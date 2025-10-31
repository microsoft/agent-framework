// Copyright (c) Microsoft. All rights reserved.

namespace Microsoft.Agents.AI.Workflows.Specialized;

/// <summary>Describes a handoff to a specific target <see cref="AIAgent"/>.</summary>
internal readonly record struct HandOffTarget(AIAgent Target, string? Reason = null)
{
    public bool Equals(HandOffTarget other) => this.Target.Id == other.Target.Id;
    public override int GetHashCode() => this.Target.Id.GetHashCode();
}
