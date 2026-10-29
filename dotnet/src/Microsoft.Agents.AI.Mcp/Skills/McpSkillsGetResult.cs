// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Text.Json.Serialization;
using ModelContextProtocol.Protocol;

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

    /// <summary>
    /// Gets the server's freshness hint for this skill. Missing or nonpositive values are immediately stale.
    /// </summary>
    [JsonPropertyName("ttlMs")]
    [JsonConverter(typeof(TimeSpanMillisecondsConverter))]
    public TimeSpan? TimeToLive { get; init; }
}
