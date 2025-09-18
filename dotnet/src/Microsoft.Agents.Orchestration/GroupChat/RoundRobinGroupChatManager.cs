// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.Orchestration;

/// <summary>
/// A <see cref="GroupChatManager"/> that selects agents in a round-robin fashion.
/// </summary>
/// <remarks>
/// Subclass this class to customize filter and user interaction behavior.
/// </remarks>
public class RoundRobinGroupChatManager : GroupChatManager
{
    private int _currentAgentIndex;

    /// <inheritdoc/>
    protected internal override ValueTask<GroupChatManagerResult<string>> FilterResultsAsync(
        IReadOnlyCollection<ChatMessage> history, CancellationToken cancellationToken = default)
    {
        GroupChatManagerResult<string> result = new(history.LastOrDefault()?.Text ?? string.Empty) { Reason = "Default result filter provides the final chat message." };
        return new ValueTask<GroupChatManagerResult<string>>(result);
    }

    /// <inheritdoc/>
    protected internal override ValueTask<GroupChatManagerResult<string>> SelectNextAgentAsync(
        IReadOnlyCollection<ChatMessage> history, GroupChatTeam team, CancellationToken cancellationToken = default)
    {
        string nextAgent = team.Skip(this._currentAgentIndex).First().Key;
        this._currentAgentIndex = (this._currentAgentIndex + 1) % team.Count;
        GroupChatManagerResult<string> result = new(nextAgent) { Reason = $"Selected agent at index: {this._currentAgentIndex}" };
        return new ValueTask<GroupChatManagerResult<string>>(result);
    }

    /// <inheritdoc/>
    protected internal override ValueTask<GroupChatManagerResult<bool>> ShouldRequestUserInputAsync(
        IReadOnlyCollection<ChatMessage> history, CancellationToken cancellationToken = default)
    {
        GroupChatManagerResult<bool> result = new(false) { Reason = "The default round-robin group chat manager does not request user input." };
        return new ValueTask<GroupChatManagerResult<bool>>(result);
    }
}
