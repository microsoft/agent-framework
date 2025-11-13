// Copyright (c) Microsoft. All rights reserved.

using System.Runtime.CompilerServices;
using Microsoft.Agents.AI;
using Microsoft.Extensions.AI;

namespace AGUIDojoClient.Components.Demos.HumanInTheLoop;

/// <summary>
/// A delegating agent that prepends instructions for the human-in-the-loop workflow.
/// </summary>
internal sealed class HumanInTheLoopAgent : DelegatingAIAgent
{
    private static readonly ChatMessage InstructionsMessage = new(
        ChatRole.System,
        """
        You help users create and execute plans. Follow this workflow:

        1. When asked to create a plan, use the `create_plan` tool with a list of step descriptions.
        2. IMMEDIATELY after creating a plan, call `confirm_plan` with the plan object to ask for user approval.
        3. Wait for the user to confirm which steps they want to proceed with.
        4. Once confirmed, use `update_plan_step` to mark steps as 'completed' as you execute them.

        IMPORTANT:
        - Always call `confirm_plan` right after `create_plan` - don't skip this step!
        - The plan parameter for `confirm_plan` should be the exact plan object returned from `create_plan`.
        - Do NOT start executing steps until the user confirms.
        - After receiving confirmation, update each selected step to 'completed' status.
        """);

    public HumanInTheLoopAgent(AIAgent innerAgent)
        : base(innerAgent)
    {
    }

    public override Task<AgentRunResponse> RunAsync(
        IEnumerable<ChatMessage> messages,
        AgentThread? thread = null,
        AgentRunOptions? options = null,
        CancellationToken cancellationToken = default)
    {
        // Prepend instructions message
        var messagesWithInstructions = messages.Prepend(InstructionsMessage);
        return base.RunAsync(messagesWithInstructions, thread, options, cancellationToken);
    }

    public override IAsyncEnumerable<AgentRunResponseUpdate> RunStreamingAsync(
        IEnumerable<ChatMessage> messages,
        AgentThread? thread = null,
        AgentRunOptions? options = null,
        CancellationToken cancellationToken = default)
    {
        // Prepend instructions message
        var messagesWithInstructions = messages.Prepend(InstructionsMessage);
        return base.RunStreamingAsync(messagesWithInstructions, thread, options, cancellationToken);
    }
}
