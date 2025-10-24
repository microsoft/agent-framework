// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using Microsoft.Agents.AI.AGUI.Shared;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.AGUI;

/// <summary>
/// Processes AG-UI event streams and maps them to MEAI abstractions.
/// </summary>
internal sealed class AGUIEventStreamProcessor
{
    /// <summary>
    /// Initializes a new instance of the <see cref="AGUIEventStreamProcessor"/> class.
    /// </summary>
    public AGUIEventStreamProcessor()
    {
    }

    /// <summary>
    /// Maps a RunStarted event to an AgentRunResponse.
    /// </summary>
    /// <param name="evt">The RunStarted event.</param>
    /// <returns>An AgentRunResponse containing RunStartedContent.</returns>
    public AgentRunResponse MapRunStarted(RunStartedEvent evt)
    {
        ChatMessage message = new(ChatRole.Assistant, [new RunStartedContent(evt.ThreadId, evt.RunId)]);
        return new AgentRunResponse(message);
    }

    /// <summary>
    /// Maps text message events to an AgentRunResponseUpdate.
    /// </summary>
    /// <param name="events">The collection of text message events.</param>
    /// <returns>An AgentRunResponseUpdate containing text content.</returns>
    public AgentRunResponseUpdate MapTextEvents(IReadOnlyList<BaseEvent> events)
    {
        string text = string.Empty;
        string? messageId = null;
        string? role = null;

        foreach (BaseEvent evt in events)
        {
            switch (evt)
            {
                case TextMessageStartEvent startEvt:
                    messageId = startEvt.MessageId;
                    role = startEvt.Role;
                    break;
                case TextMessageContentEvent contentEvt:
                    text += contentEvt.Delta;
                    messageId ??= contentEvt.MessageId;
                    break;
                case TextMessageEndEvent endEvt:
                    messageId ??= endEvt.MessageId;
                    break;
            }
        }

        ChatRole chatRole = role == "user" ? ChatRole.User : ChatRole.Assistant;
        return new AgentRunResponseUpdate(chatRole, text)
        {
            MessageId = messageId
        };
    }

    /// <summary>
    /// Maps a RunFinished event to an AgentRunResponse.
    /// </summary>
    /// <param name="evt">The RunFinished event.</param>
    /// <returns>An AgentRunResponse containing RunFinishedContent.</returns>
    public AgentRunResponse MapRunFinished(RunFinishedEvent evt)
    {
        ChatMessage message = new(ChatRole.Assistant, [new RunFinishedContent(evt.ThreadId, evt.RunId, evt.Result)]);
        return new AgentRunResponse(message);
    }

    /// <summary>
    /// Maps a RunError event to an AgentRunResponse.
    /// </summary>
    /// <param name="evt">The RunError event.</param>
    /// <returns>An AgentRunResponse containing RunErrorContent.</returns>
    public AgentRunResponse MapRunError(RunErrorEvent evt)
    {
        ChatMessage message = new(ChatRole.Assistant, [new RunErrorContent(evt.Message, evt.Code)]);
        return new AgentRunResponse(message);
    }
}
