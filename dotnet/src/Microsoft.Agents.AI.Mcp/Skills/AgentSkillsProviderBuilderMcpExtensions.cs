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
    /// <param name="client">An MCP client connected to a server exposing Agent Skills resources.</param>
    /// <param name="options">Optional options that control archive-distributed skill handling.</param>
    /// <returns>The builder instance for chaining.</returns>
    /// <remarks>
    /// <strong>Security considerations:</strong> Calling this method is an explicit opt-in to loading
    /// skills — including instructions and, for archive-type entries, extracted files — from the MCP
    /// server that <paramref name="client"/> is connected to. External skill sources may introduce
    /// adversarial or compromised skills designed to influence the agent via indirect prompt injection
    /// or to exfiltrate data through instructions or scripts the agent is induced to run. Only connect
    /// to MCP servers you trust and have evaluated, and treat their responses as untrusted input.
    /// </remarks>
    public static AgentSkillsProviderBuilder UseMcpSkills(this AgentSkillsProviderBuilder builder, McpClient client, AgentMcpSkillsSourceOptions? options = null)
    {
        _ = Throw.IfNull(builder);
        _ = Throw.IfNull(client);

        return builder.UseSource(loggerFactory => new AgentMcpSkillsSource(client, options, loggerFactory));
    }
}
