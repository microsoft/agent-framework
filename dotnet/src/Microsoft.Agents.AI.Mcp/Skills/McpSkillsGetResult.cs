// Copyright (c) Microsoft. All rights reserved.

namespace Microsoft.Agents.AI;

/// <summary>
/// Describes one skill returned by <c>skills/get</c>.
/// </summary>
internal sealed class McpSkillsGetResult
{
    /// <summary>
    /// Gets the result type, which must be <c>complete</c>.
    /// </summary>
    public required string ResultType { get; init; }

    /// <summary>
    /// Gets the skill's name, description, and resource list with expected sizes and content hashes.
    /// </summary>
    public required McpSkillEntry Skill { get; init; }
}
