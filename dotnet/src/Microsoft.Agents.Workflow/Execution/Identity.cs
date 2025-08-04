// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Diagnostics.CodeAnalysis;

namespace Microsoft.Agents.Workflows.Execution;

internal readonly struct Identity : IEquatable<Identity>
{
    public static Identity None { get; } = new Identity();

    public string? Id { get; init; }

    public bool Equals(Identity other)
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

        if (obj is Identity id)
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

    public static implicit operator Identity(string? id)
    {
        return new Identity { Id = id };
    }

    public static implicit operator string?(Identity identity)
    {
        return identity.Id;
    }
}
