// Copyright (c) Microsoft. All rights reserved.

#pragma warning disable CS0618 // Type or member is obsolete - Internal use of obsolete types for backward compatibility

using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Linq;
using System.Reflection;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Workflows.Checkpointing;
using Microsoft.Agents.AI.Workflows.Execution;
using Microsoft.Agents.AI.Workflows.Observability;
using Microsoft.Agents.AI.Workflows.Reflection;

namespace Microsoft.Agents.AI.Workflows;

internal sealed class DelayedExternalRequestContext : IExternalRequestContext
{
    public DelayedExternalRequestContext(IExternalRequestContext? targetContext = null)
    {
        this._targetContext = targetContext;
    }

    private sealed class DelayRegisteredSink : IExternalRequestSink
    {
        internal IExternalRequestSink? TargetSink { get; set; }

        public ValueTask PostAsync(ExternalRequest request) =>
            this.TargetSink is null
                ? throw new InvalidOperationException("The external request sink has not been registered yet.")
                : this.TargetSink.PostAsync(request);
    }

    private readonly Dictionary<string, (RequestPort Port, DelayRegisteredSink Sink)> _requestPorts = [];
    private IExternalRequestContext? _targetContext;

    public void ApplyPortRegistrations(IExternalRequestContext targetContext)
    {
        this._targetContext = targetContext;

        foreach ((RequestPort requestPort, DelayRegisteredSink? sink) in this._requestPorts.Values)
        {
            sink?.TargetSink = targetContext.RegisterPort(requestPort);
        }
    }

    public IExternalRequestSink RegisterPort(RequestPort port)
    {
        DelayRegisteredSink delaySink = new()
        {
            TargetSink = this._targetContext?.RegisterPort(port),
        };

        this._requestPorts.Add(port.Id, (port, delaySink));

        return delaySink;
    }
}

internal sealed class MessageTypeTranslator
{
    private readonly Dictionary<TypeId, Type> _typeLookupMap = [];
    private readonly Dictionary<Type, TypeId> _declaredTypeMap = [];

    // The types that can always be sent; this is a very inelegant solution to the following problem:
    //   Even with code analysis it is impossible to statically know all of the types that get sent via SendMessage, because
    //   IWorkflowContext can always be sent out of the current assembly (to say nothing of Reflection). This means at some
    //   level we have to register all the types being sent somewhere. Since we have to do dynamic serialization/deserialization
    //   at runtime with dependency-defined types (which we do not statically know) we need to have these types at runtime.
    //   At the same time, we should not force users to declare types to interact with core system concepts like RequestInfo.
    //   So the solution for now is to register a set of known types, at the cost of duplicating this per Executor.
    //
    //     - TODO: Create a static translation map, and keep a set of "allowed" TypeIds per Excutor.
    private static IEnumerable<Type> KnownSentTypes =>
        [
            typeof(ExternalRequest),
            typeof(ExternalResponse),

            // TurnToken?
        ];

    public MessageTypeTranslator(ISet<Type> types)
    {
        foreach (Type type in KnownSentTypes.Concat(types))
        {
            TypeId typeId = new(type);
            if (this._typeLookupMap.ContainsKey(typeId))
            {
                continue;
            }

            this._typeLookupMap[typeId] = type;
            this._declaredTypeMap[type] = typeId;
        }
    }

    public TypeId? GetDeclaredType(Type messageType)
    {
        // If the user declares a base type, the user is expected to set up any serialization to be able to deal with
        // the polymorphism transparently to the framework, or be expecting to deal with the appropriate truncation.
        for (Type? candidateType = messageType; candidateType != null; candidateType = candidateType.BaseType)
        {
            if (this._declaredTypeMap.TryGetValue(candidateType, out TypeId? declaredTypeId))
            {
                if (candidateType != messageType)
                {
                    // Add an entry for the derived type to speed up future lookups.
                    this._declaredTypeMap[messageType] = declaredTypeId;
                }

                return declaredTypeId;
            }
        }

        return null;
    }

    public Type? MapTypeId(TypeId candidateTypeId) =>
        this._typeLookupMap.TryGetValue(candidateTypeId, out Type? mappedType)
            ? mappedType
            : null;
}

internal sealed class ExecutorProtocol(MessageRouter router, ISet<Type> sendTypes, ISet<Type> yieldTypes)
{
    private readonly HashSet<TypeId> _yieldTypes = new(yieldTypes.Select(type => new TypeId(type)));

    public MessageTypeTranslator SendTypeTranslator => field ??= new MessageTypeTranslator(sendTypes);

    internal MessageRouter Router => router;

    public bool CanHandle(Type type) => router.CanHandle(type);

    public bool CanOutput(Type type) => this._yieldTypes.Contains(new(type));

    public ProtocolDescriptor Describe() => new(this.Router.IncomingTypes, yieldTypes, sendTypes, this.Router.HasCatchAll);
}

/// <summary>
/// A component that processes messages in a <see cref="Workflow"/>.
/// </summary>
[DebuggerDisplay("{GetType().Name}[{Id}]")]
public abstract class Executor : IIdentified
{
    /// <summary>
    /// A unique identifier for the executor.
    /// </summary>
    public string Id { get; }

    // TODO: Add overloads for binding with a configuration/options object once the Configured<T> hierarchy goes away.

    /// <summary>
    /// Initialize the executor with a unique identifier
    /// </summary>
    /// <param name="id">A unique identifier for the executor.</param>
    /// <param name="options">Configuration options for the executor. If <c>null</c>, default options will be used.</param>
    /// <param name="declareCrossRunShareable">Declare that this executor may be used simultaneously by multiple runs safely.</param>
    protected Executor(string id, ExecutorOptions? options = null, bool declareCrossRunShareable = false)
    {
        this.Id = id;
        this.Options = options ?? ExecutorOptions.Default;

        //if (declareCrossRunShareable && this is IResettableExecutor)
        //{
        //    // We need a way to be able to let the user override this at the workflow level too, because knowing the fine
        //    // details of when to use which of these paths seems like it could be tricky, and we should not force users
        //    // to do this; instead container agents should set this when they intiate the run (via WorkflowHostAgent).
        //    throw new ArgumentException("An executor that is declared as cross-run shareable cannot also be resettable.");
        //}

        this.IsCrossRunShareable = declareCrossRunShareable;
    }

    private DelayedExternalRequestContext DelayedPortRegistrations { get; } = new();

    internal ExecutorProtocol Protocol => field ??= this.ConfigureProtocol(new(this.DelayedPortRegistrations)).Build(this.Options);

    internal bool IsCrossRunShareable { get; }

    /// <summary>
    /// Gets the configuration options for the executor.
    /// </summary>
    protected ExecutorOptions Options { get; }

    //private bool _configuringProtocol;

    /// <summary>
    /// Configures the protocol by setting up routes and declaring the message types used for sending and yielding
    /// output.
    /// </summary>
    /// <remarks>This method serves as the primary entry point for protocol configuration. It integrates route
    /// setup and message type declarations. For backward compatibility, it is currently invoked from the
    /// RouteBuilder.</remarks>
    /// <returns>An instance of <see cref="ExecutorProtocol"/> that represents the fully configured protocol.</returns>
    protected abstract ProtocolBuilder ConfigureProtocol(ProtocolBuilder protocolBuilder);

    internal void AttachRequestContext(IExternalRequestContext externalRequestContext)
    {
        // TODO: This is an unfortunate pattern (pending the ability to rework the Configure APIs a bit):
        // new()
        // >>> will throw InvalidOperationException if AttachRequestContext() is not invoked when using PortHandlers
        //   .AttachRequestContext()
        // >>> only usable now

        this.DelayedPortRegistrations.ApplyPortRegistrations(externalRequestContext);
        _ = this.Protocol; // Force protocol to be built if not already done.
    }

    /// <summary>
    /// Perform any asynchronous initialization required by the executor. This method is called once per executor instance,
    /// </summary>
    /// <param name="context">The workflow context in which the executor executes.</param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests.
    /// The default is <see cref="CancellationToken.None"/>.</param>
    /// <returns>A <see cref="ValueTask"/> representing the asynchronous operation.</returns>
    protected internal virtual ValueTask InitializeAsync(IWorkflowContext context, CancellationToken cancellationToken = default)
        => default;

    internal MessageRouter Router => this.Protocol.Router;

    /// <summary>
    /// Process an incoming message using the registered handlers.
    /// </summary>
    /// <param name="message">The message to be processed by the executor.</param>
    /// <param name="messageType">The "declared" type of the message (captured when it was being sent). This is
    /// used to enable routing messages as their base types, in absence of true polymorphic type routing.</param>
    /// <param name="context">The workflow context in which the executor executes.</param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests.
    /// The default is <see cref="CancellationToken.None"/>.</param>
    /// <returns>A ValueTask representing the asynchronous operation, wrapping the output from the executor.</returns>
    /// <exception cref="NotSupportedException">No handler found for the message type.</exception>
    /// <exception cref="TargetInvocationException">An exception is generated while handling the message.</exception>
    public ValueTask<object?> ExecuteCoreAsync(object message, TypeId messageType, IWorkflowContext context, CancellationToken cancellationToken = default)
        => this.ExecuteCoreAsync(message, messageType, context, WorkflowTelemetryContext.Disabled, cancellationToken);

    internal async ValueTask<object?> ExecuteCoreAsync(object message, TypeId messageType, IWorkflowContext context, WorkflowTelemetryContext telemetryContext, CancellationToken cancellationToken = default)
    {
        using var activity = telemetryContext.StartExecutorProcessActivity(this.Id, this.GetType().FullName, messageType.TypeName, message);
        activity?.CreateSourceLinks(context.TraceContext);

        await context.AddEventAsync(new ExecutorInvokedEvent(this.Id, message), cancellationToken).ConfigureAwait(false);

        CallResult? result = await this.Router.RouteMessageAsync(message, context, requireRoute: true, cancellationToken)
                                              .ConfigureAwait(false);

        ExecutorEvent executionResult;
        if (result?.IsSuccess is not false)
        {
            executionResult = new ExecutorCompletedEvent(this.Id, result?.Result);
        }
        else
        {
            executionResult = new ExecutorFailedEvent(this.Id, result.Exception);
        }

        await context.AddEventAsync(executionResult, cancellationToken).ConfigureAwait(false);

        if (result is null)
        {
            throw new NotSupportedException(
                $"No handler found for message type {message.GetType().Name} in executor {this.GetType().Name}.");
        }

        if (!result.IsSuccess)
        {
            throw new TargetInvocationException($"Error invoking handler for {message.GetType()}", result.Exception);
        }

        if (result.IsVoid)
        {
            return null; // Void result.
        }

        // Output is not available if executor does not return anything, in which case
        // messages sent in the handlers of this executor will be set in the message
        // send activities.
        telemetryContext.SetExecutorOutput(activity, result.Result);

        // If we had a real return type, raise it as a SendMessage; TODO: Should we have a way to disable this behaviour?
        if (result.Result is not null && this.Options.AutoSendMessageHandlerResultObject)
        {
            await context.SendMessageAsync(result.Result, cancellationToken: cancellationToken).ConfigureAwait(false);
        }
        if (result.Result is not null && this.Options.AutoYieldOutputHandlerResultObject)
        {
            await context.YieldOutputAsync(result.Result, cancellationToken).ConfigureAwait(false);
        }

        return result.Result;
    }

    /// <summary>
    /// Invoked before a checkpoint is saved, allowing custom pre-save logic in derived classes.
    /// </summary>
    /// <param name="context">The workflow context.</param>
    /// <returns>A ValueTask representing the asynchronous operation.</returns>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests.
    /// The default is <see cref="CancellationToken.None"/>.</param>
    protected internal virtual ValueTask OnCheckpointingAsync(IWorkflowContext context, CancellationToken cancellationToken = default) => default;

    /// <summary>
    /// Invoked after a checkpoint is loaded, allowing custom post-load logic in derived classes.
    /// </summary>
    /// <param name="context">The workflow context.</param>
    /// <returns>A ValueTask representing the asynchronous operation.</returns>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests.
    /// The default is <see cref="CancellationToken.None"/>.</param>
    protected internal virtual ValueTask OnCheckpointRestoredAsync(IWorkflowContext context, CancellationToken cancellationToken = default) => default;

    /// <summary>
    /// A set of <see cref="Type"/>s, representing the messages this executor can handle.
    /// </summary>
    public ISet<Type> InputTypes => this.Router.IncomingTypes;

    /// <summary>
    /// A set of <see cref="Type"/>s, representing the messages this executor can produce as output.
    /// </summary>
    public ISet<Type> OutputTypes => field ??= new HashSet<Type>(this.Protocol.Describe().Yields);

    /// <summary>
    /// Describes the protocol for communication with this <see cref="Executor"/>.
    /// </summary>
    /// <returns></returns>
    public ProtocolDescriptor DescribeProtocol() => this.Protocol.Describe();

    /// <summary>
    /// Checks if the executor can handle a specific message type.
    /// </summary>
    /// <param name="messageType"></param>
    /// <returns></returns>
    public bool CanHandle(Type messageType) => this.Protocol.CanHandle(messageType);

    internal bool CanOutput(Type messageType) => this.Protocol.CanOutput(messageType);
}

/// <summary>
/// Provides a simple executor implementation that uses a single message handler function to process incoming messages.
/// </summary>
/// <typeparam name="TInput">The type of input message.</typeparam>
/// <param name="id">A unique identifier for the executor.</param>
/// <param name="options">Configuration options for the executor. If <c>null</c>, default options will be used.</param>
/// <param name="declareCrossRunShareable">Declare that this executor may be used simultaneously by multiple runs safely.</param>
public abstract class Executor<TInput>(string id, ExecutorOptions? options = null, bool declareCrossRunShareable = false)
    : Executor(id, options, declareCrossRunShareable), IMessageHandler<TInput>
{
    /// <inheritdoc/>
    protected override ProtocolBuilder ConfigureProtocol(ProtocolBuilder protocolBuilder)
    {
        Func<TInput, IWorkflowContext, CancellationToken, ValueTask> handlerDelegate = this.HandleAsync;

        return protocolBuilder.ConfigureRoutes(routeBuilder => routeBuilder.AddHandler(handlerDelegate))
                              .AddMethodAttributeTypes(handlerDelegate.Method)
                              .AddClassAttributeTypes(this.GetType());
    }

    /// <inheritdoc/>
    public abstract ValueTask HandleAsync(TInput message, IWorkflowContext context, CancellationToken cancellationToken = default);
}

/// <summary>
/// Provides a simple executor implementation that uses a single message handler function to process incoming messages.
/// </summary>
/// <typeparam name="TInput">The type of input message.</typeparam>
/// <typeparam name="TOutput">The type of output message.</typeparam>
/// <param name="id">A unique identifier for the executor.</param>
/// <param name="options">Configuration options for the executor. If <c>null</c>, default options will be used.</param>
/// <param name="declareCrossRunShareable">Declare that this executor may be used simultaneously by multiple runs safely.</param>
public abstract class Executor<TInput, TOutput>(string id, ExecutorOptions? options = null, bool declareCrossRunShareable = false)
    : Executor(id, options ?? ExecutorOptions.Default, declareCrossRunShareable),
      IMessageHandler<TInput, TOutput>
{
    /// <inheritdoc/>
    protected override ProtocolBuilder ConfigureProtocol(ProtocolBuilder protocolBuilder)
    {
        Func<TInput, IWorkflowContext, CancellationToken, ValueTask<TOutput>> handlerDelegate = this.HandleAsync;

        return protocolBuilder.ConfigureRoutes(routeBuilder => routeBuilder.AddHandler(handlerDelegate))
                              .AddMethodAttributeTypes(handlerDelegate.Method)
                              .AddClassAttributeTypes(this.GetType());
    }

    /// <inheritdoc/>
    public abstract ValueTask<TOutput> HandleAsync(TInput message, IWorkflowContext context, CancellationToken cancellationToken = default);
}
