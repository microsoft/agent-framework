// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json;
using AGUI.Abstractions;
using AGUI.Server;
using Microsoft.Agents.AI;
using Microsoft.Extensions.AI;

namespace RecipeAssistant;

/// <summary>
/// A thin agent that reads the client's current recipe from the AG-UI <see cref="RunAgentInput.State"/>
/// and prepends it to the conversation as a system message, so the model edits the existing recipe
/// instead of starting over. This handles the input side of shared state only. The output side is
/// declarative: the inner agent's <c>generate_recipe</c> tool result becomes a <c>STATE_SNAPSHOT</c>
/// via <c>AGUIStreamOptions.MapResultAsStateSnapshot</c>.
/// </summary>
internal sealed class RecipeStateAgent(AIAgent innerAgent) : DelegatingAIAgent(innerAgent)
{
    protected override Task<AgentResponse> RunCoreAsync(
        IEnumerable<ChatMessage> messages,
        AgentSession? session = null,
        AgentRunOptions? options = null,
        CancellationToken cancellationToken = default) =>
        this.RunCoreStreamingAsync(messages, session, options, cancellationToken)
            .ToAgentResponseAsync(cancellationToken);

    protected override IAsyncEnumerable<AgentResponseUpdate> RunCoreStreamingAsync(
        IEnumerable<ChatMessage> messages,
        AgentSession? session = null,
        AgentRunOptions? options = null,
        CancellationToken cancellationToken = default)
    {
        if (options is ChatClientAgentRunOptions { ChatOptions: { } chatOptions } &&
            chatOptions.TryGetRunAgentInput(out RunAgentInput? input) &&
            input.State is { ValueKind: JsonValueKind.Object } state)
        {
            ChatMessage stateMessage = new(
                ChatRole.System,
                $"The user's current recipe state is:\n{state.GetRawText()}");
            messages = [stateMessage, .. messages];
        }

        return this.InnerAgent.RunStreamingAsync(messages, session, options, cancellationToken);
    }
}
