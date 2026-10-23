// Copyright (c) Microsoft. All rights reserved.

namespace Microsoft.Agents.AI;

/// <summary>
/// Configuration options for <see cref="AgentMcpSkillsSource"/>.
/// </summary>
/// <remarks>
/// Listed discovery limits bound page counts and total skill counts.
/// The listed resource size limit separately bounds resource content processed by this source.
/// These limits do not bound incoming message size, list-response JSON size, or total memory consumption.
/// Application developers are responsible for evaluating server trustworthiness and configuring appropriate
/// input-size and resource limits through their chosen MCP client, transport, or hosting environment.
/// See <see cref="AgentSkillsProviderBuilderMcpExtensions.UseMcpSkills"/> for security considerations.
/// </remarks>
public sealed class AgentMcpSkillsSourceOptions
{
    /// <summary>
    /// Gets or sets the maximum number of <c>skills/list</c> pages requested per discovery.
    /// </summary>
    /// <remarks>
    /// When <see langword="null"/>, defaults to <c>10</c>. Must be positive.
    /// Empty pages count toward this limit. Discovery fails rather than returning a partial catalog
    /// when the last allowed page includes a continuation cursor.
    /// </remarks>
    public int? ListedMaxPageCount { get; set; }

    /// <summary>
    /// Gets or sets the maximum number of skills accepted across all <c>skills/list</c> pages per discovery.
    /// </summary>
    /// <remarks>
    /// When <see langword="null"/>, defaults to <c>100</c>. Must be positive.
    /// Every entry counts, including duplicate skill URIs. Discovery fails if the limit is exceeded.
    /// </remarks>
    public int? ListedMaxSkillCount { get; set; }

    /// <summary>
    /// Gets or sets the maximum size, in bytes, of a resource discovered through <c>skills/list</c>,
    /// including <c>SKILL.md</c>.
    /// </summary>
    /// <remarks>
    /// When <see langword="null"/>, defaults to <c>1 MiB</c> (<c>1,048,576</c> bytes).
    /// Must be positive. Discovery rejects resources whose advertised sizes exceed the limit.
    /// Reads also check actual UTF-8 text and decoded binary sizes before encoding text or decoding
    /// blobs for integrity verification.
    /// There is no combined resource-size limit per skill.
    /// </remarks>
    public long? ListedResourceMaxSizeBytes { get; set; }
}
