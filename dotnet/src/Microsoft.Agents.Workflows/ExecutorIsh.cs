// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.Workflows.Specialized;
using Microsoft.Extensions.AI.Agents;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.Workflows;

///// <summary>
///// A delegate representing a method that handles a message of type <typeparamref name="TMessage"/> and produces
///// an output message of type <typeparamref name="TResult"/>.
///// </summary>
///// <typeparam name="TMessage"></typeparam>
///// <typeparam name="TResult"></typeparam>
///// <param name="message"></param>
///// <param name="context"></param>
///// <param name="cancellation"></param>
///// <returns></returns>
//public delegate ValueTask<TResult> MessageHandler<in TMessage, TResult>(TMessage message, IWorkflowContext context, CancellationToken cancellation = default);

///// <summary>
///// A delegate representing a method that handles a message of type <typeparamref name="TMessage"/>
///// </summary>
///// <typeparam name="TMessage"></typeparam>
///// <param name="message"></param>
///// <param name="context"></param>
///// <param name="cancellation"></param>
///// <returns></returns>
//public delegate ValueTask MessageHandler<in TMessage>(TMessage message, IWorkflowContext context, CancellationToken cancellation = default);

/// <summary>
/// Extension methods for configuring executors and functions as <see cref="ExecutorIsh"/> instances.
/// </summary>
public static class ExecutorIshConfigurationExtensions
{
    /// <summary>
    /// .
    /// </summary>
    /// <typeparam name="TExecutor"></typeparam>
    /// <typeparam name="TOptions"></typeparam>
    /// <param name="factoryAsync"></param>
    /// <param name="id"></param>
    /// <param name="options"></param>
    /// <returns></returns>
    public static ExecutorIsh Configure<TExecutor, TOptions>(this Func<Config<TOptions>, ValueTask<TExecutor>> factoryAsync, string id, TOptions? options = null)
        where TExecutor : Executor
        where TOptions : ExecutorOptions
    {
        Configured<TExecutor, TOptions> configured = new(factoryAsync, id, options);

        return new ExecutorIsh(configured.Super<TExecutor, Executor, TOptions>(), typeof(TExecutor), ExecutorIsh.Type.Executor);
    }

    private static ExecutorIsh ToExecutorIsh<TInput>(this FunctionExecutor<TInput> executor, Delegate raw)
    {
        return new ExecutorIsh(executor.Configure(raw: raw)
                                       .Super<FunctionExecutor<TInput>, Executor>(),
                               typeof(FunctionExecutor<TInput>),
                               ExecutorIsh.Type.Function);
    }

    private static ExecutorIsh ToExecutorIsh<TInput, TOutput>(this FunctionExecutor<TInput, TOutput> executor, Delegate raw)
    {
        return new ExecutorIsh(executor.Configure(raw: raw)
                                       .Super<FunctionExecutor<TInput, TOutput>, Executor>(),
                               typeof(FunctionExecutor<TInput, TOutput>),
                               ExecutorIsh.Type.Function);
    }

    /// <summary>
    /// .
    /// </summary>
    /// <typeparam name="TInput"></typeparam>
    /// <param name="messageHandlerAsync"></param>
    /// <param name="id"></param>
    /// <param name="options"></param>
    /// <returns></returns>
    public static ExecutorIsh Configure<TInput>(this Func<TInput, IWorkflowContext, CancellationToken, ValueTask> messageHandlerAsync, string id, ExecutorOptions? options = null)
        => new FunctionExecutor<TInput>(messageHandlerAsync, id, options).ToExecutorIsh(messageHandlerAsync);

    /// <summary>
    /// .
    /// </summary>
    /// <typeparam name="TInput"></typeparam>
    /// <typeparam name="TOutput"></typeparam>
    /// <param name="messageHandlerAsync"></param>
    /// <param name="id"></param>
    /// <param name="options"></param>
    /// <returns></returns>
    public static ExecutorIsh Configure<TInput, TOutput>(this Func<TInput, IWorkflowContext, CancellationToken, ValueTask<TOutput>> messageHandlerAsync, string id, ExecutorOptions? options = null)
        => new FunctionExecutor<TInput, TOutput>(messageHandlerAsync, id, options).ToExecutorIsh(messageHandlerAsync);
}

/// <summary>
/// A tagged union representing an object that can function like an <see cref="Executor"/> in a <see cref="Workflow"/>,
/// or a reference to one by ID.
/// </summary>
public sealed class ExecutorIsh :
    IIdentified,
    IEquatable<ExecutorIsh>,
    IEquatable<IIdentified>,
    IEquatable<string>
{
    /// <summary>
    /// The type of the <see cref="ExecutorIsh"/>.
    /// </summary>
    public enum Type
    {
        /// <summary>
        /// An unbound executor reference, identified only by ID.
        /// </summary>
        Unbound,
        /// <summary>
        /// An actual <see cref="Executor"/> instance.
        /// </summary>
        Executor,
        /// <summary>
        /// A function delegate to be wrapped as an executor.
        /// </summary>
        Function,
        /// <summary>
        /// An <see cref="InputPort"/> for servicing external requests.
        /// </summary>
        InputPort,
        /// <summary>
        /// An <see cref="AIAgent"/> instance.
        /// </summary>
        Agent,
    }

    /// <summary>
    /// Gets the type of data contained in this <see cref="ExecutorIsh" /> instance.
    /// </summary>
    public Type ExecutorType { get; init; }

    private readonly string? _idValue;

    private readonly Configured<Executor>? _configuredExecutor;
    private readonly System.Type? _configuredExecutorType;

    internal readonly InputPort? _inputPortValue;
    private readonly AIAgent? _aiAgentValue;

    /// <summary>
    /// Initializes a new instance of the <see cref="ExecutorIsh"/> class as an unbound reference by ID.
    /// </summary>
    /// <param name="id">A unique identifier for an <see cref="Executor"/> in the <see cref="Workflow"/></param>
    public ExecutorIsh(string id)
    {
        this.ExecutorType = Type.Unbound;
        this._idValue = Throw.IfNull(id);
    }

    internal ExecutorIsh(Configured<Executor> configured, System.Type configuredExecutorType, ExecutorIsh.Type type)
    {
        this.ExecutorType = type;
        this._configuredExecutor = configured;
        this._configuredExecutorType = configuredExecutorType;
    }

    /// <summary>
    /// Initializes a new instance of the ExecutorIsh class using the specified executor.
    /// </summary>
    /// <param name="executor">The executor instance to be wrapped.</param>
    public ExecutorIsh(Executor executor)
    {
        this.ExecutorType = Type.Executor;
        this._configuredExecutor = Throw.IfNull(executor).Configure();
        this._configuredExecutorType = executor.GetType();
    }

    /// <summary>
    /// Initializes a new instance of the ExecutorIsh class using the specified input port.
    /// </summary>
    /// <param name="port">The input port to associate to be wrapped.</param>
    public ExecutorIsh(InputPort port)
    {
        this.ExecutorType = Type.InputPort;
        this._inputPortValue = Throw.IfNull(port);
    }

    /// <summary>
    /// Initializes a new instance of the ExecutorIsh class using the specified AI agent.
    /// </summary>
    /// <param name="aiAgent"></param>
    public ExecutorIsh(AIAgent aiAgent)
    {
        this.ExecutorType = Type.Agent;
        this._aiAgentValue = Throw.IfNull(aiAgent);
    }

    internal bool IsUnbound => this.ExecutorType == Type.Unbound;

    /// <inheritdoc/>
    public string Id => this.ExecutorType switch
    {
        Type.Unbound => this._idValue ?? throw new InvalidOperationException("This ExecutorIsh is unbound and has no ID."),
        Type.Executor => this._configuredExecutor!.Id,
        Type.InputPort => this._inputPortValue!.Id,
        Type.Agent => this._aiAgentValue!.Id,
        Type.Function => this._configuredExecutor!.Id,
        _ => throw new InvalidOperationException($"Unknown ExecutorIsh type: {this.ExecutorType}")
    };

    internal object? RawData => this.ExecutorType switch
    {
        Type.Unbound => this._idValue,
        Type.Executor => this._configuredExecutor!.Raw ?? this._configuredExecutor,
        Type.InputPort => this._inputPortValue,
        Type.Agent => this._aiAgentValue,
        Type.Function => this._configuredExecutor!.Raw ?? this._configuredExecutor,
        _ => throw new InvalidOperationException($"Unknown ExecutorIsh type: {this.ExecutorType}")
    };

    /// <summary>
    /// Gets the registration details for the current executor.
    /// </summary>
    /// <remarks>The returned registration depends on the type of the executor. If the executor is unbound, an
    /// <see cref="InvalidOperationException"/> is thrown. For other executor types, the registration  includes the
    /// appropriate ID, type, and provider based on the executor's configuration.</remarks>
    internal ExecutorRegistration Registration => new(this.Id, this.RuntimeType, this.ExecutorProvider, this.RawData);

    private System.Type RuntimeType => this.ExecutorType switch
    {
        Type.Unbound => throw new InvalidOperationException($"ExecutorIsh with ID '{this.Id}' is unbound."),
        Type.Executor => this._configuredExecutorType!,
        Type.InputPort => typeof(RequestInfoExecutor),
        Type.Agent => typeof(AIAgentHostExecutor),
        Type.Function => this._configuredExecutorType!,
        _ => throw new InvalidOperationException($"Unknown ExecutorIsh type: {this.ExecutorType}")
    };

    /// <summary>
    /// Gets an <see cref="Func{Executor}"/> that can be used to obtain an <see cref="Executor"/> instance
    /// corresponding to this <see cref="ExecutorIsh"/>.
    /// </summary>
    private Func<ValueTask<Executor>> ExecutorProvider => this.ExecutorType switch
    {
        Type.Unbound => throw new InvalidOperationException($"Executor with ID '{this.Id}' is unbound."),
        Type.Executor => this._configuredExecutor!.BoundFactoryAsync,
        Type.InputPort => () => new(new RequestInfoExecutor(this._inputPortValue!)),
        Type.Agent => () => new(new AIAgentHostExecutor(this._aiAgentValue!)),
        Type.Function => this._configuredExecutor!.BoundFactoryAsync,
        _ => throw new InvalidOperationException($"Unknown ExecutorIsh type: {this.ExecutorType}")
    };

    /// <summary>
    /// Defines an implicit conversion from an <see cref="Executor"/> instance to an <see cref="ExecutorIsh"/> object.
    /// </summary>
    /// <param name="executor">The <see cref="Executor"/> instance to convert to <see cref="ExecutorIsh"/>.</param>
    public static implicit operator ExecutorIsh(Executor executor) => new(executor);

    /// <summary>
    /// Defines an implicit conversion from an <see cref="InputPort"/> to an <see cref="ExecutorIsh"/> instance.
    /// </summary>
    /// <param name="inputPort">The <see cref="InputPort"/> to convert to an <see cref="ExecutorIsh"/>.</param>
    public static implicit operator ExecutorIsh(InputPort inputPort) => new(inputPort);

    /// <summary>
    /// Defines an implicit conversion from an <see cref="AIAgent"/> to an <see cref="ExecutorIsh"/> instance.
    /// </summary>
    /// <param name="aiAgent">The <see cref="AIAgent"/> to convert to an <see cref="ExecutorIsh"/>.</param>
    public static implicit operator ExecutorIsh(AIAgent aiAgent) => new(aiAgent);

    /// <summary>
    /// Defines an implicit conversion from a string to an <see cref="ExecutorIsh"/> instance.
    /// </summary>
    /// <param name="id">The string ID to convert to an <see cref="ExecutorIsh"/>.</param>
    public static implicit operator ExecutorIsh(string id)
    {
        return new ExecutorIsh(id);
    }

    /// <inheritdoc/>
    public bool Equals(ExecutorIsh? other)
    {
        return other is not null &&
               other.Id == this.Id;
    }

    /// <inheritdoc/>
    public bool Equals(IIdentified? other)
    {
        return other is not null &&
               other.Id == this.Id;
    }

    /// <inheritdoc/>
    public bool Equals(string? other)
    {
        return other is not null &&
               other == this.Id;
    }

    /// <inheritdoc/>
    public override bool Equals(object? obj)
    {
        if (obj is null)
        {
            return false;
        }

        if (obj is ExecutorIsh ish)
        {
            return this.Equals(ish);
        }
        else if (obj is IIdentified identified)
        {
            return this.Equals(identified);
        }
        else if (obj is string str)
        {
            return this.Equals(str);
        }

        return false;
    }

    /// <inheritdoc/>
    public override int GetHashCode()
    {
        return this.Id.GetHashCode();
    }

    /// <inheritdoc/>
    public override string ToString()
    {
        return this.ExecutorType switch
        {
            Type.Unbound => $"'{this.Id}':<unbound>",
            Type.Executor => $"'{this.Id}':{this._configuredExecutorType!.Name}",
            Type.InputPort => $"'{this.Id}':Input({this._inputPortValue!.Request.Name}->{this._inputPortValue!.Response.Name})",
            Type.Agent => $"{this.Id}':AIAgent(@{this._aiAgentValue!.GetType().Name})",
            Type.Function => $"'{this.Id}':{this._configuredExecutorType!.Name}",
            _ => $"'{this.Id}':<unknown[{this.ExecutorType}]>"
        };
    }
}
