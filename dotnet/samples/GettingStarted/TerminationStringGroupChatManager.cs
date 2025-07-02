// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.Orchestration.GroupChat;
using Microsoft.Extensions.AI;

namespace GettingStarted;

internal class TerminationStringGroupChatManager(string approvalString) : RoundRobinGroupChatManager
{
    public override async ValueTask<GroupChatManagerResult<bool>> ShouldTerminate(IReadOnlyCollection<ChatMessage> history, CancellationToken cancellationToken = default)
    {
        var baseResult = await base.ShouldTerminate(history, cancellationToken);
        if (baseResult.Value)
        {
            return baseResult;
        }

        if (history.Select(m => m.Text).Any(text => text.Contains(approvalString, StringComparison.OrdinalIgnoreCase)))
        {
            return new GroupChatManagerResult<bool>(true)
            {
                Reason = $"Approval string '{approvalString}' found in chat history."
            };
        }

        return new GroupChatManagerResult<bool>(false)
        {
            Reason = $"Approval string '{approvalString}' not found in chat history."
        };
    }
}
