// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Diagnostics.CodeAnalysis;
using System.Text.Json;
using Microsoft.Extensions.AI;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI;

/// <summary>
/// Provides extension methods for <see cref="AgentSession"/>.
/// </summary>
public static class AgentSessionExtensions
{
    /// <summary>
    /// Attempts to retrieve the in-memory chat history messages associated with the specified agent session, if the agent is storing memories in the session using the <see cref="InMemoryChatHistoryProvider"/>
    /// </summary>
    /// <remarks>
    /// This method is only applicable when using <see cref="InMemoryChatHistoryProvider"/> and if the service does not require in-service chat history storage.
    /// </remarks>
    /// <param name="session">The agent session from which to retrieve in-memory chat history.</param>
    /// <param name="messages">When this method returns, contains the list of chat history messages if available; otherwise, null.</param>
    /// <param name="stateKey">An optional key used to identify the chat history state in the session's state bag. If null, the default key for
    /// in-memory chat history is used.</param>
    /// <param name="jsonSerializerOptions">Optional JSON serializer options to use when accessing the session state. If null, default options are used.</param>
    /// <returns><see langword="true"/> if the in-memory chat history messages were found and retrieved; <see langword="false"/> otherwise.</returns>
    public static bool TryGetInMemoryChatHistory(this AgentSession session, [MaybeNullWhen(false)] out List<ChatMessage> messages, string? stateKey = null, JsonSerializerOptions? jsonSerializerOptions = null)
    {
        _ = Throw.IfNull(session);

        if (session.StateBag.TryGetValue(stateKey ?? nameof(InMemoryChatHistoryProvider), out InMemoryChatHistoryProvider.State? state, jsonSerializerOptions ?? AgentAbstractionsJsonUtilities.DefaultOptions) && state?.Messages is not null)
        {
            messages = state.Messages;
            return true;
        }

        messages = null;
        return false;
    }

    /// <summary>
    /// Sets the in-memory chat message history for the specified agent session, replacing any existing messages.
    /// </summary>
    /// <remarks>
    /// This method is only applicable when using <see cref="InMemoryChatHistoryProvider"/> and if the service does not require in-service chat history storage.
    /// If messages are set, but a different <see cref="ChatHistoryProvider"/> is used, or if chat history is stored in the underlying AI service, the messages will be ignored.
    /// </remarks>
    /// <param name="session">The agent session whose in-memory chat history will be updated.</param>
    /// <param name="messages">The list of chat messages to store in memory for the session. Replaces any existing messages for the specified
    /// state key.</param>
    /// <param name="stateKey">The key used to identify the in-memory chat history within the session's state bag. If null, a default key is
    /// used.</param>
    /// <param name="jsonSerializerOptions">The serializer options used when accessing or storing the state. If null, default options are applied.</param>
    public static void SetInMemoryChatHistory(this AgentSession session, List<ChatMessage> messages, string? stateKey = null, JsonSerializerOptions? jsonSerializerOptions = null)
    {
        _ = Throw.IfNull(session);

        if (session.StateBag.TryGetValue(stateKey ?? nameof(InMemoryChatHistoryProvider), out InMemoryChatHistoryProvider.State? state, jsonSerializerOptions ?? AgentAbstractionsJsonUtilities.DefaultOptions) && state is not null)
        {
            state.Messages = messages;
            return;
        }

        session.StateBag.SetValue(stateKey ?? nameof(InMemoryChatHistoryProvider), new InMemoryChatHistoryProvider.State() { Messages = messages }, jsonSerializerOptions ?? AgentAbstractionsJsonUtilities.DefaultOptions);
    }
}
