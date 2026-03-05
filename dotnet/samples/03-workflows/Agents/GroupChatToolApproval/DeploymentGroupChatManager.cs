// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.AI;
using Microsoft.Agents.AI.Workflows;
using Microsoft.Extensions.AI;

namespace WorkflowGroupChatToolApprovalSample;

/// <summary>
/// Custom GroupChatManager that selects the next speaker based on the conversation flow.
/// </summary>
/// <remarks>
/// This simple selector follows a predefined flow:
/// 1. QA Engineer runs tests
/// 2. DevOps Engineer checks staging and creates rollback plan
/// 3. DevOps Engineer deploys to production (triggers approval)
/// </remarks>
internal sealed class DeploymentGroupChatManager : GroupChatManager
{
    private readonly IReadOnlyList<AIAgent> _agents;

    public DeploymentGroupChatManager(IReadOnlyList<AIAgent> agents)
    {
        this._agents = agents;
    }

    protected override ValueTask<AIAgent> SelectNextAgentAsync(
        IReadOnlyList<ChatMessage> history,
        CancellationToken cancellationToken = default)
    {
        if (history.Count == 0)
        {
            throw new InvalidOperationException("Conversation is empty; cannot select next speaker.");
        }

        // First speaker after initial user message
        if (this.IterationCount == 0)
        {
            AIAgent qaAgent = this._agents.First(a => a.Name == "QAEngineer");
            return new ValueTask<AIAgent>(qaAgent);
        }

        // Subsequent speakers are DevOps Engineer
        AIAgent devopsAgent = this._agents.First(a => a.Name == "DevOpsEngineer");
        return new ValueTask<AIAgent>(devopsAgent);
    }
}
