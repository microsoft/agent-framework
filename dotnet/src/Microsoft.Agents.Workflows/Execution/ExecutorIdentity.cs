// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Diagnostics.CodeAnalysis;

namespace Microsoft.Agents.Workflows.Execution;

internal readonly struct ExecutorIdentity : IEquatable<ExecutorIdentity>
{
    public static ExecutorIdentity None { get; } = new ExecutorIdentity();

    public string? Id { get; init; }

    public bool Equals(ExecutorIdentity other)
    {
        return this.Id == null
            ? other.Id == null
            : other.Id != null && StringComparer.OrdinalIgnoreCase.Equals(this.Id, other.Id);
    }

    public override bool Equals([NotNullWhen(true)] object? obj)
    {
        if (this.Id == null)
        {
            return obj == null;
        }

        if (obj == null)
        {
            return false;
        }

        if (obj is ExecutorIdentity id)
        {
            return id.Equals(this);
        }

        if (obj is string idStr)
        {
            return StringComparer.OrdinalIgnoreCase.Equals(this.Id, idStr);
        }

        return false;
    }

    public override int GetHashCode()
    {
        return this.Id == null ? 0 : StringComparer.OrdinalIgnoreCase.GetHashCode(this.Id);
    }

    public static implicit operator ExecutorIdentity(string? id)
    {
        return new ExecutorIdentity { Id = id };
    }

    public static implicit operator string?(ExecutorIdentity identity)
    {
        return identity.Id;
    }
}
