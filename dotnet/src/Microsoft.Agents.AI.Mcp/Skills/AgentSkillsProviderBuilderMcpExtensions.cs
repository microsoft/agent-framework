// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Shared.Diagnostics;
using ModelContextProtocol.Client;

namespace Microsoft.Agents.AI;

/// <summary>
/// Adds MCP skill sources to an <see cref="AgentSkillsProviderBuilder"/>.
/// </summary>
public static class AgentSkillsProviderBuilderMcpExtensions
{
    /// <summary>
    /// Adds skills from the MCP server connected to the supplied <paramref name="client"/>.
    /// </summary>
    /// <param name="builder">The builder to extend.</param>
    /// <param name="client">An MCP client connected to a server that supports <c>skills/list</c>.</param>
    /// <param name="options">Optional TTL resolver and limits for listing pages, skill counts, and resource sizes.</param>
    /// <returns>The builder for chaining calls.</returns>
    /// <remarks>
    /// <para>
    /// The server must declare the <c>io.modelcontextprotocol/skills</c> extension.
    /// Otherwise, the source returns an empty list without sending a request.
    /// Each skill's instructions are stored in <c>SKILL.md</c>.
    /// This file and supporting resources are fetched only when requested.
    /// The caller retains ownership of <paramref name="client"/>.
    /// </para>
    /// <para>
    /// The MCP source manages caching using the server's time to live (TTL) values.
    /// Configure <see cref="AgentMcpSkillsSourceOptions.TtlResolver"/> to override TTLs for list pages, skill metadata, and resources.
    /// Call <see cref="AgentSkillsProviderBuilder.DisableCaching"/> and disable other caches around
    /// this source so it can refresh the skill list when its cached data expires.
    /// </para>
    /// <code>
    /// var provider = new AgentSkillsProviderBuilder()
    ///     .UseMcpSkills(client)
    ///     .DisableCaching()
    ///     .Build();
    /// </code>
    /// <para>
    /// When combining MCP skills with other sources, cache only the sources that need it.
    /// Pass the combined source directly to <see cref="AgentSkillsProvider"/>:
    /// </para>
    /// <code>
    /// var source = new AggregatingAgentSkillsSource(
    /// [
    ///     new CachingAgentSkillsSource(otherSource),
    ///     new AgentMcpSkillsSource(client),
    /// ]);
    ///
    /// using var provider = new AgentSkillsProvider(source, ownsSource: true);
    /// </code>
    /// <para>
    /// A skill refresh returns a new object with updated resource URIs, sizes, and content hashes.
    /// Existing skill objects keep those earlier values. Callers must load the new object to use the update.
    /// See <see cref="AgentMcpSkillsSource"/> for resource validation, caching, and refresh behavior.
    /// </para>
    /// <para>
    /// <strong>Security:</strong> Only connect to servers you trust and treat their content as untrusted input.
    /// Malicious instructions or scripts can manipulate the agent or expose data.
    /// The configured limits do not bound incoming message size or total memory use.
    /// Configure input-size limits in the MCP client, transport, or host as needed.
    /// </para>
    /// </remarks>
    public static AgentSkillsProviderBuilder UseMcpSkills(this AgentSkillsProviderBuilder builder, McpClient client, AgentMcpSkillsSourceOptions? options = null)
    {
        _ = Throw.IfNull(builder);
        _ = Throw.IfNull(client);

        return builder.UseSource(loggerFactory => new AgentMcpSkillsSource(client, options, loggerFactory));
    }
}
