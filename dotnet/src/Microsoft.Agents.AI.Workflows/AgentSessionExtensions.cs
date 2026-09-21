// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Diagnostics.CodeAnalysis;
using Microsoft.Agents.AI;
using Microsoft.Extensions.AI;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI.Workflows;

/// <summary>
/// Provides extension methods for <see cref="AgentSession"/>.
/// </summary>
public static class AgentSessionExtensions
{
    /// <summary>
    /// Attempts to retrieve the workflow chat history messages associated with the specified agent session, if the agent is storing memories in the session using the <see cref="WorkflowChatHistoryProvider"/>
    /// </summary>
    /// <remarks>
    /// This method is only applicable when using <see cref="WorkflowChatHistoryProvider"/> and if the service does not require in-service chat history storage.
    /// </remarks>
    /// <param name="session">The agent session from which to retrieve workflow chat history.</param>
    /// <param name="messages">When this method returns, contains the list of chat history messages if available; otherwise, null.</param>
    /// <returns><see langword="true"/> if the workflow chat history messages were found and retrieved; <see langword="false"/> otherwise.</returns>
    public static bool TryGetWorkflowChatHistory(this AgentSession session, [MaybeNullWhen(false)] out IEnumerable<ChatMessage> messages)
    {
        _ = Throw.IfNull(session);

        if (session is WorkflowSession workflowSession)
        {
            messages = workflowSession.ChatHistoryProvider.GetAllMessages(session);
            return true;
        }

        messages = null;
        return false;
    }

    /// <summary>
    /// Adds messages to the workflow chat message history for the specified agent session.
    /// </summary>
    /// <remarks>
    /// This method is only applicable when using <see cref="WorkflowChatHistoryProvider"/> and if the service does not require in-service chat history storage.
    /// If messages are set, but a different <see cref="WorkflowChatHistoryProvider"/> is used, or if chat history is stored in the underlying AI service, the messages will be ignored.
    /// </remarks>
    /// <param name="session">The agent session whose workflow chat history will be updated.</param>
    /// <param name="messages">The list of chat messages to store in memory for the session. Replaces any existing messages for the specified
    /// state key.</param>
    public static void AddMessagesToWorkflowChatHistory(this AgentSession session, IEnumerable<ChatMessage> messages)
    {
        _ = Throw.IfNull(session);

        if (session is WorkflowSession workflowSession)
        {
            workflowSession.ChatHistoryProvider.AddMessages(session, messages);
        }
    }
}
