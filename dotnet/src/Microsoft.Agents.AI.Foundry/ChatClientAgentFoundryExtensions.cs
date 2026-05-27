// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Threading;
using System.Threading.Tasks;
using Azure.AI.Extensions.OpenAI;
using Azure.AI.Projects.Agents;
using Microsoft.Extensions.AI;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI.Foundry;

/// <summary>
/// Foundry-specific extensions on <see cref="ChatClientAgent"/>. Mirrors Python's free
/// <c>to_prompt_agent(agent)</c> function for agents whose underlying chat client is a
/// <see cref="FoundryChatClient"/>.
/// </summary>
public static class ChatClientAgentFoundryExtensions
{
    /// <summary>
    /// Converts the supplied agent into a <see cref="ProjectsAgentDefinition"/> ready to publish
    /// via <c>AgentAdministrationClient.CreateAgentVersionAsync</c>.
    /// </summary>
    /// <remarks>
    /// Only works on agents whose chat client is a <see cref="FoundryChatClient"/> and whose
    /// construction mode is convertible. The Agent Endpoint construction mode (Mode 3) is not
    /// convertible because no local definition exists; conversion in that case throws.
    /// </remarks>
    /// <param name="agent">The chat client agent to convert.</param>
    /// <param name="cancellationToken">A token that can cancel an internal server-side fetch when the agent was constructed from a bare <see cref="AgentReference"/>.</param>
    /// <returns>A <see cref="ProjectsAgentDefinition"/> suitable for publishing.</returns>
    /// <exception cref="ArgumentNullException"><paramref name="agent"/> is <see langword="null"/>.</exception>
    /// <exception cref="InvalidOperationException">The agent's chat client is not a <see cref="FoundryChatClient"/>; the agent was constructed via the Agent Endpoint mode (Mode 3); no model id is set on the agent's <see cref="ChatOptions"/> for the Responses Agent mode (Mode 1); or the agent contains an <see cref="AITool"/> that cannot be converted to a <c>ResponseTool</c>.</exception>
    public static Task<ProjectsAgentDefinition> ToPromptAgentAsync(this ChatClientAgent agent, CancellationToken cancellationToken = default)
    {
        Throw.IfNull(agent);
        return FoundryPromptAgentConverter.ConvertAsync(agent.ChatClient, agent.GetService<ChatOptions>(), cancellationToken);
    }
}
