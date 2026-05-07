// Copyright (c) Microsoft. All rights reserved.

using System.Runtime.CompilerServices;
using System.Text.Json;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI;

/// <summary>
/// A minimal <see cref="AIAgent"/> that echoes the user's input text back as the response.
/// No LLM or external service is required.
/// </summary>
public sealed class EchoAIAgent : AIAgent
{
    /// <inheritdoc/>
    public override string Name => "echo-agent";

    /// <inheritdoc/>
    public override string Description => "An agent that echoes back the input message.";

    /// <inheritdoc/>
    protected override Task<AgentResponse> RunCoreAsync(
        IEnumerable<ChatMessage> messages,
        AgentSession? session = null,
        AgentRunOptions? options = null,
        CancellationToken cancellationToken = default)
    {
        var inputText = GetInputText(messages);
        var response = new AgentResponse(new ChatMessage(ChatRole.Assistant, $"Echo: {inputText}"));
        return Task.FromResult(response);
    }

    /// <inheritdoc/>
    protected override async IAsyncEnumerable<AgentResponseUpdate> RunCoreStreamingAsync(
        IEnumerable<ChatMessage> messages,
        AgentSession? session = null,
        AgentRunOptions? options = null,
        [EnumeratorCancellation] CancellationToken cancellationToken = default)
    {
        var inputText = GetInputText(messages);
        yield return new AgentResponseUpdate
        {
            Role = ChatRole.Assistant,
            Contents = [new TextContent($"Echo: {inputText}")],
        };

        await Task.CompletedTask;
    }

    /// <inheritdoc/>
    protected override ValueTask<AgentSession> CreateSessionCoreAsync(CancellationToken cancellationToken = default)
        => new(new EchoAgentSession());

    /// <inheritdoc/>
    protected override ValueTask<JsonElement> SerializeSessionCoreAsync(
        AgentSession session,
        JsonSerializerOptions? jsonSerializerOptions = null,
        CancellationToken cancellationToken = default)
        => new(JsonSerializer.SerializeToElement(new { }, jsonSerializerOptions));

    /// <inheritdoc/>
    protected override ValueTask<AgentSession> DeserializeSessionCoreAsync(
        JsonElement serializedState,
        JsonSerializerOptions? jsonSerializerOptions = null,
        CancellationToken cancellationToken = default)
        => new(new EchoAgentSession());

    private static string GetInputText(IEnumerable<ChatMessage> messages)
    {
        foreach (var message in messages)
        {
            if (message.Role == ChatRole.User)
            {
                return message.Text ?? string.Empty;
            }
        }

        return string.Empty;
    }

    /// <summary>
    /// Minimal session for the echo agent. No state is persisted.
    /// </summary>
    private sealed class EchoAgentSession : AgentSession;
}
