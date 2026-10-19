// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Shared.Diagnostics;
using ModelContextProtocol.Client;

namespace Microsoft.Agents.AI;

/// <summary>
/// MCP-specific extension methods for <see cref="AgentSkillsProviderBuilder"/>.
/// </summary>
public static class AgentSkillsProviderBuilderMcpExtensions
{
    /// <summary>
    /// Adds a skill source that discovers skills served over MCP via the supplied <paramref name="client"/>.
    /// </summary>
    /// <param name="builder">The builder to extend.</param>
    /// <param name="client">An MCP client connected to a server that supports <c>skills/list</c> or <c>skill://index.json</c>.</param>
    /// <param name="options">Optional options that control skill loading.</param>
    /// <returns>The builder instance for chaining.</returns>
    /// <remarks>
    /// <para>
    /// Supports skills discovered through <c>skills/list</c> when the server declares the
    /// <c>io.modelcontextprotocol/skills</c> extension. Otherwise, discovers skills through
    /// <c>skill://index.json</c>.
    /// Listed skills fetch instructions and supporting resources when requested.
    /// Page counts, total skill counts, and individual resource sizes
    /// are bounded by <see cref="AgentMcpSkillsSourceOptions"/>.
    /// These checks do not limit incoming messages before the supplied client receives and parses them.
    /// </para>
    /// <para>
    /// Listed skill discovery is based on the Skills extension specification incorporating the
    /// working group's decision dated <c>2026-09-08</c>.
    /// Support currently includes skill discovery through <c>skills/list</c> and reading listed skill resources,
    /// but not the full extension.
    /// </para>
    /// <para>
    /// Index-based discovery and archive-distributed skills are compatibility features and will be deprecated
    /// in a future release.
    /// </para>
    /// <para>
    /// <strong>Security considerations:</strong> Calling this method is an explicit opt-in to loading
    /// skills — including instructions and, for archive-type entries, extracted files — from the MCP
    /// server that <paramref name="client"/> is connected to. External skill sources may introduce
    /// adversarial or compromised skills designed to influence the agent via indirect prompt injection
    /// or to exfiltrate data through instructions or scripts the agent is induced to run. Only connect
    /// to MCP servers you trust and have evaluated, and treat their responses as untrusted input.
    /// </para>
    /// <para>
    /// This source does not impose a byte limit on individual or combined <c>skills/list</c> responses.
    /// Page-count, skill-count, and resource-size limits do not bound incoming message size or total
    /// memory consumption. A malicious, compromised, or misconfigured server can return oversized
    /// responses that cause excessive memory consumption. Application developers are responsible for
    /// configuring appropriate input-size and resource limits through their chosen MCP client, transport,
    /// or hosting environment.
    /// </para>
    /// </remarks>
    public static AgentSkillsProviderBuilder UseMcpSkills(this AgentSkillsProviderBuilder builder, McpClient client, AgentMcpSkillsSourceOptions? options = null)
    {
        _ = Throw.IfNull(builder);
        _ = Throw.IfNull(client);

        return builder.UseSource(loggerFactory => new AgentMcpSkillsSource(client, options, loggerFactory));
    }
}
