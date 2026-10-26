// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Extensions.AI;
using Microsoft.Shared.Diagnostics;

namespace A2A;

/// <summary>
/// Extension methods for the <see cref="TaskStatus"/> class.
/// </summary>
internal static class AgentTaskStatusExtensions
{
    internal static ChatMessage? ToChatMessage(this TaskStatus status)
    {
        _ = Throw.IfNull(status);

        // Status messages are optional, even for unsuccessful tasks.
        if (status.Message is null)
        {
            return null;
        }

        // Skip status messages for routine progress and successful completion.
        if (status.State is TaskState.Submitted or TaskState.Working or TaskState.Completed)
        {
            return null;
        }

        // Convert status messages for InputRequired, AuthRequired, Failed, Canceled, Rejected, and Unspecified.
        var message = status.Message.ToChatMessage();

        return message.Contents.Count > 0 ? message : null;
    }
}
