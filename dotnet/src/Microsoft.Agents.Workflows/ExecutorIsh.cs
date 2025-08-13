// Copyright (c) Microsoft. All rights reserved.

using System;
using Microsoft.Agents.Workflows.Specialized;
using Microsoft.Extensions.AI.Agents;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.Workflows;

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
    private readonly Executor? _executorValue;
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

    /// <summary>
    /// Initializes a new instance of the ExecutorIsh class using the specified executor.
    /// </summary>
    /// <param name="executor">The executor instance to be wrapped.</param>
    public ExecutorIsh(Executor executor)
    {
        this.ExecutorType = Type.Executor;
        this._executorValue = Throw.IfNull(executor);
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
        Type.Executor => this._executorValue!.Id,
        Type.InputPort => this._inputPortValue!.Id,
        Type.Agent => this._aiAgentValue!.Id,
        _ => throw new InvalidOperationException($"Unknown ExecutorIsh type: {this.ExecutorType}")
    };

    /// <summary>
    /// Gets an <see cref="ExecutorProvider{T}"/> that can be used to obtain an <see cref="Executor"/> instance
    /// corresponding to this <see cref="ExecutorIsh"/>.
    /// </summary>
    public ExecutorProvider<Executor> ExecutorProvider => this.ExecutorType switch
    {
        Type.Unbound => throw new InvalidOperationException($"Executor with ID '{this.Id}' is unbound."),
        Type.Executor => () => this._executorValue!,
        Type.InputPort => () => new RequestInputExecutor(this._inputPortValue!),
        Type.Agent => () => new AIAgentHostExecutor(this._aiAgentValue!),
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
            Type.Executor => $"'{this.Id}':{this._executorValue!.GetType().Name}",
            Type.InputPort => $"'{this.Id}':Input({this._inputPortValue!.Request.Name}->{this._inputPortValue!.Response.Name})",
            Type.Agent => $"{this.Id}':AIAgent(@{this._aiAgentValue!.GetType().Name})",
            _ => $"'{this.Id}':<unknown[{this.ExecutorType}]>"
        };
    }
}
