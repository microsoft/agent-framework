// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Diagnostics.CodeAnalysis;

namespace Microsoft.Agents.Workflows.Execution;

internal readonly struct ExecutorIdentity : IEquatable<ExecutorIdentity>
{
    public static ExecutorIdentity None { get; }

    public string? Id { get; init; }

    public bool Equals(ExecutorIdentity other) =>
        this.Id is null
            ? other.Id is null
            : other.Id is not null && StringComparer.OrdinalIgnoreCase.Equals(this.Id, other.Id);

    public override bool Equals([NotNullWhen(true)] object? obj)
    {
        if (this.Id is null)
        {
            return obj is null;
        }

        if (obj is null)
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

    public override int GetHashCode() => this.Id is null ? 0 : StringComparer.OrdinalIgnoreCase.GetHashCode(this.Id);

    public static implicit operator ExecutorIdentity(string? id) => new() { Id = id };

    public static implicit operator string?(ExecutorIdentity identity) => identity.Id;
}
