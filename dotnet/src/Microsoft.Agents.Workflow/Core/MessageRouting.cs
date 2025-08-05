// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Diagnostics.CodeAnalysis;
using System.Linq;
using System.Reflection;
using System.Threading.Tasks;
using Microsoft.Shared.Diagnostics;

using HandlerInfosT =
    System.Collections.Generic.Dictionary<
        System.Type,
        Microsoft.Agents.Workflows.Core.MessageHandlerInfo
    >;

namespace Microsoft.Agents.Workflows.Core;

/// <summary>
/// This attribute indicates that a message handler streams messages during its execution.
/// </summary>
[AttributeUsage(AttributeTargets.Class | AttributeTargets.Method, AllowMultiple = true)]
public sealed class StreamsMessageAttribute : Attribute
{
    /// <summary>
    /// The type of the message that the handler yields.
    /// </summary>
    public Type Type { get; }

    /// <summary>
    /// Indicates that the message handler yields streaming messages during the course of execution.
    /// </summary>
    public StreamsMessageAttribute(Type type)
    {
        // This attribute is used to mark executors that yield messages.
        this.Type = type ?? throw new ArgumentNullException(nameof(type), "Type cannot be null.");
    }
}

/// <summary>
/// This class represents the result of a call to a <see cref="IMessageHandler{TMessage}"/>
/// or <see cref="IMessageHandler{TMessage,TResult}"/>.
/// </summary>
public sealed class CallResult
{
    /// <summary>
    /// Indicates whether the call was void (i.e., no result expected). This only applies to
    /// calls to <see cref="IMessageHandler{TMessage}"/> handlers.
    /// </summary>
    public bool IsVoid { get; init; }

    /// <summary>
    /// If the call was successful, this property contains the result of the call. For calls to
    /// void handlers, this will be <c>null</c>.
    /// </summary>
    public object? Result { get; init; } = null;

    /// <summary>
    /// If the call failed, this property contains the exception that was raised during the call.
    /// </summary>
    public Exception? Exception { get; init; } = null;

    /// <summary>
    /// Indicates whether the call was successful. A call is considered successful if it returned
    /// without throwing an exception.
    /// </summary>
    public bool IsSuccess => this.Exception == null;

    private CallResult(bool isVoid = false)
    {
        // Private constructor to enforce use of static methods.
        this.IsVoid = isVoid;
    }

    /// <summary>
    /// Create a <see cref="CallResult"/> indicating a successful that returned a result (non-void).
    /// </summary>
    /// <param name="result">The result to return.</param>
    /// <returns>A <see cref="CallResult"/> indicating the result of the call.</returns>
    public static CallResult ReturnResult(object? result = null)
    {
        return new() { Result = result };
    }

    /// <summary>
    /// Create a <see cref="CallResult"/> indicating a successful call that returned no result (void).
    /// </summary>
    /// <returns>A <see cref="CallResult"/> indicating the result of the call.</returns>
    public static CallResult ReturnVoid()
    {
        return new(isVoid: true);
    }

    /// <summary>
    /// Create a <see cref="CallResult"/> indicating that an exception was raised during the call.
    /// </summary>
    /// <param name="wasVoid">A boolean specifying whether the call was void (was not expected to return
    /// a value).</param>
    /// <param name="exception">The exception that was raised during the call.</param>
    /// <returns>A <see cref="CallResult"/> indicating the result of the call.</returns>
    /// <exception cref="ArgumentNullException">Thrown when <paramref name="exception"/> is null.</exception>
    public static CallResult RaisedException(bool wasVoid, Exception exception)
    {
        if (exception == null)
        {
            throw new ArgumentNullException(nameof(exception), "Exception cannot be null.");
        }

        return new(wasVoid) { Exception = exception };
    }
}

internal struct MessageHandlerInfo
{
    public Type InType { get; init; }
    public Type? OutType { get; init; } = null;

    public MethodInfo HandlerInfo { get; init; }
    public Func<object, ValueTask<object?>>? Unwrapper { get; init; } = null;

    [SuppressMessage("AOT", "IL3050:Calling members annotated with 'RequiresDynamicCodeAttribute' may break functionality " +
        "when AOT compiling.", Justification = "<Pending>")]
    public MessageHandlerInfo(MethodInfo handlerInfo)
    {
        // The method is one of the following:
        //   - ValueTask HandleAsync(TMessage message, IExecutionContext context)
        //   - ValueTask<TResult> HandleAsync(TMessage message, IExecutionContext context)
        this.HandlerInfo = handlerInfo;

        ParameterInfo[] parameters = handlerInfo.GetParameters();
        if (parameters.Length != 2)
        {
            throw new ArgumentException("Handler method must have exactly two parameters: TMessage and IExecutionContext.", nameof(handlerInfo));
        }

        if (parameters[1].ParameterType != typeof(IWorkflowContext))
        {
            throw new ArgumentException("Handler method's second parameter must be of type IExecutionContext.", nameof(handlerInfo));
        }

        this.InType = parameters[0].ParameterType;

        Type decoratedReturnType = handlerInfo.ReturnType;
        if (decoratedReturnType.IsGenericType && decoratedReturnType.GetGenericTypeDefinition() == typeof(ValueTask<>))
        {
            // If the return type is ValueTask<TResult>, extract TResult.
            Type[] returnRawTypes = decoratedReturnType.GetGenericArguments();
            Debug.Assert(
                returnRawTypes.Length == 1,
                "ValueTask<TResult> should have exactly one generic argument.");

            this.OutType = returnRawTypes.Single();
            this.Unwrapper = ValueTaskTypeErasure.UnwrapperFor(this.OutType);
        }
        else if (decoratedReturnType == typeof(ValueTask))
        {
            // If the return type is ValueTask, there is no output type.
            this.OutType = null;
        }
        else
        {
            throw new ArgumentException("Handler method must return ValueTask or ValueTask<TResult>.", nameof(handlerInfo));
        }
    }

    public static Func<object, IWorkflowContext, ValueTask<CallResult>> Bind(Func<object, IWorkflowContext, object?> handlerAsync, bool checkType, Type? resultType = null, Func<object, ValueTask<object?>>? unwrapper = null)
    {
        return InvokeHandlerAsync;

        async ValueTask<CallResult> InvokeHandlerAsync(object message, IWorkflowContext workflowContext)
        {
            bool expectingVoid = resultType == null || resultType == typeof(void);

            try
            {
                object? maybeValueTask = handlerAsync(message, workflowContext);

                if (expectingVoid)
                {
                    if (maybeValueTask is ValueTask vt)
                    {
                        await vt.ConfigureAwait(false);
                        return CallResult.ReturnVoid();
                    }

                    throw new InvalidOperationException(
                        "Handler method is expected to return ValueTask or ValueTask<TResult>, but returned " +
                        $"{maybeValueTask?.GetType().Name ?? "null"}.");
                }

                Debug.Assert(resultType != null, "Expected resultType to be non-null when not expecting void.");
                if (unwrapper == null)
                {
                    throw new InvalidOperationException(
                        $"Handler method is expected to return ValueTask<{resultType!.Name}>, but no unwrapper is available.");
                }

                if (maybeValueTask == null)
                {
                    throw new InvalidOperationException(
                        $"Handler method returned null, but a ValueTask<{resultType!.Name}> was expected.");
                }

                object? result = await unwrapper(maybeValueTask).ConfigureAwait(false);

                if (checkType && result != null && !resultType.IsInstanceOfType(result))
                {
                    throw new InvalidOperationException(
                        $"Handler method returned an incompatible type: expected {resultType.Name}, got {result.GetType().Name}.");
                }

                return CallResult.ReturnResult(result);
            }
            catch (Exception ex)
            {
                // If the handler throws an exception, return it in the CallResult.
                return CallResult.RaisedException(wasVoid: expectingVoid, exception: ex);
            }
        }
    }

    public Func<object, IWorkflowContext, ValueTask<CallResult>> Bind(Executor executor, bool checkType = false)
    {
        MethodInfo handlerMethod = this.HandlerInfo;
        return MessageHandlerInfo.Bind(InvokeHandler, checkType, this.OutType, this.Unwrapper);

        object? InvokeHandler(object message, IWorkflowContext workflowContext)
        {
            return handlerMethod.Invoke(executor, new object[] { message, workflowContext });
        }
    }
}

internal class MessageRouter
{
    // TODO: The goal of the cache is to allow SourceGenerators to do the reflection to bind the handlers in the router.
    internal static readonly Dictionary<Type, Func<MessageRouter>> s_routerFactoryCache = new();

    private Dictionary<Type, Func<object, IWorkflowContext, ValueTask<CallResult>>> BoundHandlers { get; init; } = new();
    private IDefaultMessageHandler? DefaultHandler { get; init; } = null;

    [SuppressMessage("Trimming",
        "IL2075:'this' argument does not satisfy 'DynamicallyAccessedMembersAttribute' in call to target method. The return value " +
        "of the source method does not have matching annotations.",
        Justification = "Trimming attributes are inaccessible in 472")]
    [SuppressMessage("Trimming",
        "IL2070:'this' argument does not satisfy 'DynamicallyAccessedMembersAttribute' in call to target method. The parameter of " +
        "method does not have matching annotations.",
        Justification = "Trimming attributes are inaccessible in 472")]
    private static HandlerInfosT ReflectHandlers(Type executorType)
    {
        // This method reflects over the methods of the executor type to find message handlers.
        HandlerInfosT handlers = new();

        // Get all implementations of IMessageHandler<TMessage> or IMessageHandler<TMessage, TResult>
        // and create a MessageHandlerInfo for each.
        if (!typeof(Executor).IsAssignableFrom(executorType))
        {
            throw new ArgumentException($"Type {executorType.FullName} is not a valid Executor type.", nameof(executorType));
        }

        if (executorType.IsAbstract || executorType.IsInterface)
        {
            throw new ArgumentException($"Type {executorType.FullName} cannot be abstract or an interface.", nameof(executorType));
        }

        // Iterate all interfaces implemented by the executor type.
        foreach (Type interfaceType in executorType.GetInterfaces())
        {
            // Check if the interface is a message handler.
            if (!interfaceType.IsGenericType)
            {
                continue;
            }

            if (interfaceType.IsGenericType && (interfaceType.GetGenericTypeDefinition() == typeof(IMessageHandler<>) ||
                                                interfaceType.GetGenericTypeDefinition() == typeof(IMessageHandler<,>)))
            {
                // Get the generic arguments of the interface.
                Type[] genericArguments = interfaceType.GetGenericArguments();
                if (genericArguments.Length < 1 || genericArguments.Length > 2)
                {
                    continue; // Invalid handler signature.
                }
                Type inType = genericArguments[0];
                Type? outType = genericArguments.Length == 2 ? genericArguments[1] : null;
                MethodInfo? method = interfaceType.GetMethod("HandleAsync");
                if (method != null)
                {
                    MessageHandlerInfo info = new(method) { InType = inType, OutType = outType };
                    handlers[inType] = info;
                }
            }
        }

        return handlers;
    }

    [SuppressMessage("Trimming",
        "IL2075:'this' argument does not satisfy 'DynamicallyAccessedMembersAttribute' in call to target method. The return value " +
        "of the source method does not have matching annotations.",
        Justification = "Trimming attributes are inaccessible in 472")]
    internal static HandlerInfosT ReflectHandlers<TExecutor>() where TExecutor : Executor
        => ReflectHandlers(typeof(TExecutor));

    internal static MessageRouter BindMessageHandlers(Executor executor, bool checkType)
    {
        if (s_routerFactoryCache.TryGetValue(executor.GetType(), out var factory))
        {
            return factory();
        }

        // If no factory is found, reflect over the handlers
        HandlerInfosT handlers = ReflectHandlers(executor.GetType());

        Dictionary<Type, Func<object, IWorkflowContext, ValueTask<CallResult>>> boundHandlers = new();
        foreach (Type inType in handlers.Keys)
        {
            MessageHandlerInfo handlerInfo = handlers[inType];
            Func<object, IWorkflowContext, ValueTask<CallResult>> boundHandler = handlerInfo.Bind(executor, checkType);
            boundHandlers.Add(inType, boundHandler); // TODO: Turn the error here into something more actionable.
        }

        return new MessageRouter(boundHandlers, executor as IDefaultMessageHandler);
    }

    internal MessageRouter(Dictionary<Type, Func<object, IWorkflowContext, ValueTask<CallResult>>> handlers, IDefaultMessageHandler? defaultHandler = null)
    {
        this.BoundHandlers = handlers;
        this.DefaultHandler = defaultHandler;
    }

    /// <summary>
    /// .
    /// </summary>
    /// <param name="message"></param>
    /// <param name="context"></param>
    /// <param name="requireRoute"></param>
    /// <returns></returns>
    /// <exception cref="ArgumentNullException"></exception>
    /// <exception cref="NotImplementedException"></exception>
    public async ValueTask<CallResult?> RouteMessageAsync(object message, IWorkflowContext context, bool requireRoute = false)
    {
        if (message == null)
        {
            throw new ArgumentNullException(nameof(message), "Message cannot be null.");
        }

        // TODO: Implement base type delegation?
        CallResult? result = null;
        if (this.BoundHandlers.TryGetValue(message.GetType(), out Func<object, IWorkflowContext, ValueTask<CallResult>>? handler))
        {
            result = await handler(message, context).ConfigureAwait(false);
        }
        else if (this.DefaultHandler != null)
        {
            try
            {
                await this.DefaultHandler.HandleAsync(message, context).ConfigureAwait(false);
                result = CallResult.ReturnVoid();
            }
            catch (Exception e)
            {
                result = CallResult.RaisedException(wasVoid: true, e);
            }
        }

        return result;
    }

    public bool CanHandle(object message) => this.CanHandle(Throw.IfNull(message).GetType());

    public bool CanHandle(Type candidateType)
    {
        Throw.IfNull(candidateType);

        // Check if the router can handle the candidate type.
        return this.DefaultHandler != null || this.BoundHandlers.ContainsKey(candidateType);
    }

    public HashSet<Type> IncomingTypes
        => this.DefaultHandler != null
            ? [.. this.BoundHandlers.Keys, typeof(object)]
            : [.. this.BoundHandlers.Keys];
}
