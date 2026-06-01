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
    /// <returns>The builder instance for chaining.</returns>
    public static AgentSkillsProviderBuilder UseMcpSkills(this AgentSkillsProviderBuilder builder, McpClient client)
    {
        _ = Throw.IfNull(builder);
        _ = Throw.IfNull(client);

        return builder.UseSource(new AgentMcpSkillsSource(client));
    }
}
