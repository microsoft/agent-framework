// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Hosting.OpenAI;

/// <summary>
/// The result of converting an OpenAI Responses request body into Agent Framework run values via
/// <see cref="OpenAIResponses.ToAgentRunRequest(System.Text.Json.JsonElement, OpenAIResponsesMapOptions?)"/>.
/// </summary>
/// <remarks>
/// This type carries the values an application passes to <see cref="AIAgent.RunAsync(IEnumerable{ChatMessage}, AgentSession?, AgentRunOptions?, System.Threading.CancellationToken)"/>
/// (or the streaming equivalent) when it owns its own hosting route. It does not run the agent; the
/// application remains in control of when and how the run happens.
/// </remarks>
public sealed class OpenAIResponsesRunRequest
{
    internal OpenAIResponsesRunRequest(IList<ChatMessage> messages, AgentRunOptions? options, string? previousResponseId = null, string? conversationId = null)
    {
        this.Messages = messages;
        this.Options = options;
        this.PreviousResponseId = previousResponseId;
        this.ConversationId = conversationId;
    }

    /// <summary>
    /// Gets the chat messages parsed from the request body, ready to pass to an <see cref="AIAgent"/> run.
    /// </summary>
    public IList<ChatMessage> Messages { get; }

    /// <summary>
    /// Gets the run options mapped from the request, or <see langword="null"/> when no request setting is
    /// mapped onto the run. The mapping is controlled by <see cref="OpenAIResponsesMapOptions.RunOptionsFactory"/>;
    /// by default no request setting is mapped.
    /// </summary>
    public AgentRunOptions? Options { get; }

    /// <summary>
    /// Gets the request's <c>previous_response_id</c> continuation pointer, or <see langword="null"/> when absent.
    /// This changes each turn (it follows the response chain), so it is not a stable partition key.
    /// </summary>
    public string? PreviousResponseId { get; }

    /// <summary>
    /// Gets the request's <c>conversation</c> id, or <see langword="null"/> when absent. Unlike
    /// <see cref="PreviousResponseId"/>, this is stable across turns, so it is a valid stable partition key.
    /// </summary>
    public string? ConversationId { get; }
}
