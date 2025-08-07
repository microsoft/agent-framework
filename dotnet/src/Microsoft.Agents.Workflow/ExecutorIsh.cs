// Copyright (c) Microsoft. All rights reserved.

using System;
using Microsoft.Agents.Workflows.Core;
using Microsoft.Agents.Workflows.Specialized;
using Microsoft.Extensions.AI.Agents;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.Workflows;

/// <summary>
/// .
/// </summary>
public sealed class ExecutorIsh :
    IIdentified,
    IEquatable<ExecutorIsh>,
    IEquatable<IIdentified>,
    IEquatable<string>
{
    /// <summary>
    /// .
    /// </summary>
    public enum Type
    {
        /// <summary>
        /// .
        /// </summary>
        Unbound,
        /// <summary>
        /// .
        /// </summary>
        Executor,
        /// <summary>
        /// .
        /// </summary>
        InputPort,
        /// <summary>
        /// .
        /// </summary>
        Agent,
        //ProcessStep
    }

    /// <summary>
    /// .
    /// </summary>
    public Type ExecutorType { get; init; }

    private readonly string? _idValue;
    private readonly Executor? _executorValue;
    internal readonly InputPort? _inputPortValue;
    private readonly AIAgent? _aiAgentValue;

    /// <summary>
    /// .
    /// </summary>
    /// <param name="id"></param>
    public ExecutorIsh(string id)
    {
        this.ExecutorType = Type.Unbound;
        this._idValue = Throw.IfNull(id);
    }

    /// <summary>
    /// .
    /// </summary>
    /// <param name="executor"></param>
    public ExecutorIsh(Executor executor)
    {
        this.ExecutorType = Type.Executor;
        this._executorValue = Throw.IfNull(executor);
    }

    /// <summary>
    /// .
    /// </summary>
    /// <param name="port"></param>
    public ExecutorIsh(InputPort port)
    {
        this.ExecutorType = Type.InputPort;
        this._inputPortValue = Throw.IfNull(port);
    }

    /// <summary>
    /// .
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
        //Type.ProcessStep => throw new NotImplementedException("ProcessStep type is not yet implemented."),
        _ => throw new InvalidOperationException($"Unknown ExecutorIsh type: {this.ExecutorType}")
    };

    /// <summary>
    /// .
    /// </summary>
    public ExecutorProvider<Executor> ExecutorProvider => this.ExecutorType switch
    {
        Type.Unbound => throw new InvalidOperationException($"Executor with ID '{this.Id}' is unbound."),
        Type.Executor => () => this._executorValue!,
        Type.InputPort => () => new RequestInputExecutor(this._inputPortValue!),
        Type.Agent => () => new AIAgentHostExecutor(this._aiAgentValue!),
        //Type.ProcessStep => throw new NotImplementedException("ProcessStep type is not yet implemented."),
        _ => throw new InvalidOperationException($"Unknown ExecutorIsh type: {this.ExecutorType}")
    };

    /// <summary>
    /// .
    /// </summary>
    /// <param name="executor"></param>
    public static implicit operator ExecutorIsh(Executor executor) => new(executor);

    /// <summary>
    /// .
    /// </summary>
    /// <param name="inputPort"></param>
    public static implicit operator ExecutorIsh(InputPort inputPort) => new(inputPort);

    /// <summary>
    /// .
    /// </summary>
    /// <param name="aiAgent"></param>
    public static implicit operator ExecutorIsh(AIAgent aiAgent) => new(aiAgent);

    /// <summary>
    /// .
    /// </summary>
    /// <param name="id"></param>
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
            //Type.ProcessStep => $"ExecutorIsh for ProcessStep with ID '{this.Id}'",
            _ => $"'{this.Id}':<unknown[{this.ExecutorType}]>"
        };
    }
}
