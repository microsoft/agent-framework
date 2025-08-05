// Copyright (c) Microsoft. All rights reserved.

using System;
using Microsoft.Agents.Workflows.Core;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.Workflows;

internal sealed class ExecutorIsh :
    IIdentified,
    IEquatable<ExecutorIsh>,
    IEquatable<IIdentified>,
    IEquatable<string>
{
    public enum Type
    {
        Unbound,
        Executor,
        //Function,
        //Agent,
        //ProcessStep
    }

    public Type ExecutorType { get; init; }

    private readonly string? _idValue;
    private readonly Executor? _executorValue;
    //private readonly Func<object?, CallResult>? _functionValue;

    public ExecutorIsh(Executor executor)
    {
        this.ExecutorType = Type.Executor;
        this._executorValue = Throw.IfNull(executor);
    }

    public ExecutorIsh(string id)
    {
        this.ExecutorType = Type.Unbound;
        this._idValue = Throw.IfNull(id);
    }

    public bool IsUnbound => this.ExecutorType == Type.Unbound;

    public string Id => this.ExecutorType switch
    {
        Type.Unbound => this._idValue ?? throw new InvalidOperationException("This ExecutorIsh is unbound and has no ID."),
        Type.Executor => this._executorValue!.Id,
        //Type.Function => throw new NotImplementedException("Function type is not yet implemented."),
        //Type.Agent => throw new NotImplementedException("Agent type is not yet implemented."),
        //Type.ProcessStep => throw new NotImplementedException("ProcessStep type is not yet implemented."),
        _ => throw new ArgumentOutOfRangeException(nameof(this.ExecutorType), "Unknown ExecutorIsh type.")
    };

    public ExecutorProvider<Executor> ExecutorProvider => this.ExecutorType switch
    {
        Type.Unbound => throw new InvalidOperationException($"Executor with ID '{this.Id}' is unbound."),
        Type.Executor => () => this._executorValue!,
        //Type.Function => throw new NotImplementedException("Function type is not yet implemented."),
        //Type.Agent => throw new NotImplementedException("Agent type is not yet implemented."),
        //Type.ProcessStep => throw new NotImplementedException("ProcessStep type is not yet implemented."),
        _ => throw new ArgumentOutOfRangeException(nameof(this.ExecutorType), "Unknown ExecutorIsh type.")
    };

    //public ExecutorIsh(Func<object?, CallResult> function)
    //{
    //    this.ExecutorType = Type.Function;
    //    this._functionValue = Throw.IfNull(function);
    //}

    // Implicit conversions into ExecutorIsh
    public static implicit operator ExecutorIsh(Executor executor)
    {
        return new ExecutorIsh(executor);
    }

    // How do we AoT compile this?
    //public static implicit operator ExecutorIsh(Func<object?, CallResult> function)
    //{
    //    return new ExecutorIsh(function);
    //}

    public static implicit operator ExecutorIsh(string id)
    {
        return new ExecutorIsh(id);
    }

    public bool Equals(ExecutorIsh? other)
    {
        return other is not null &&
               other.Id == this.Id;
    }

    public bool Equals(IIdentified? other)
    {
        return other is not null &&
               other.Id == this.Id;
    }

    public bool Equals(string? other)
    {
        return other is not null &&
               other == this.Id;
    }

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

    public override int GetHashCode()
    {
        return this.Id.GetHashCode();
    }

    public override string ToString()
    {
        return this.ExecutorType switch
        {
            Type.Unbound => $"'{this.Id}':<unbound>",
            Type.Executor => $"'{this.Id}':{this._executorValue!.GetType()}",
            //Type.Function => $"ExecutorIsh for Function with ID '{this.Id}'",
            //Type.Agent => $"ExecutorIsh for Agent with ID '{this.Id}'",
            //Type.ProcessStep => $"ExecutorIsh for ProcessStep with ID '{this.Id}'",
            _ => throw new ArgumentOutOfRangeException(nameof(this.ExecutorType), "Unknown ExecutorIsh type.")
        };
    }
}
