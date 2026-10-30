// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Linq;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Workflows.Specialized.Magentic;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Workflows.UnitTests;

public class MagenticOrchestratorTests
{
    [Theory]
    [InlineData(null)]
    [InlineData("worker")]
    public async Task Checkpoint_Without_Review_State_Preserves_Plan_ProgressAsync(string? currentSpeaker)
    {
        // Arrange
        TestReplayAgent manager = new(
        [
            [new(ChatRole.Assistant, """
                {
                    "is_request_satisfied": { "answer": true, "reason": "Done" },
                    "is_in_loop": { "answer": false, "reason": "Done" },
                    "is_progress_being_made": { "answer": true, "reason": "Done" },
                    "next_speaker": { "answer": "Worker", "reason": "Done" },
                    "instruction_or_question": { "answer": "Done", "reason": "Done" }
                }
                """)],
            [new(ChatRole.Assistant, "Task completed")]
        ], name: "Manager");
        TestEchoAgent participant = new(name: "Worker");
        MagenticOrchestrator orchestrator = new(manager, [participant], new(), requirePlanSignoff: true);
        TestWorkflowContext context = new(orchestrator.Id);
        MagenticTaskState taskState = new(
            [new(ChatRole.User, "Complete the task")],
            [],
            new(new(ChatRole.Assistant, "Facts"), new(ChatRole.Assistant, "Plan")),
            null, new(), false, null);
        await context.QueueStateUpdateAsync(MagenticConstants.MagenticTaskContextKey, taskState);
        await context.QueueStateUpdateAsync(MagenticConstants.CurrentSpeakerStateKey, currentSpeaker);

        // Act
        await orchestrator.OnCheckpointRestoredAsync(context);
        await orchestrator.TakeTurnAsync(new TurnToken(), context);

        // Assert
        Assert.Empty(context.SentMessages);
        if (currentSpeaker is null)
        {
            Assert.Equal(0, manager.Turn);
            Assert.Empty(context.YieldedOutputs);
            Assert.Single(context.EmittedEvents.OfType<WorkflowWarningEvent>());
        }
        else
        {
            Assert.Equal(2, manager.Turn);
            Assert.Single(context.YieldedOutputs);
            Assert.Empty(context.EmittedEvents.OfType<WorkflowWarningEvent>());
        }
    }

    [Fact]
    public void Test_MagenticOrchestrator_Protocol_Declares_SentMessages()
    {
        TestReplayAgent manager = new(name: nameof(MagenticOrchestrator));
        TestEchoAgent participant = new(name: "Echo");
        MagenticOrchestrator orchestrator = new(manager, [participant], new(), requirePlanSignoff: false);

        ProtocolDescriptor protocol = orchestrator.DescribeProtocol();

        Assert.Contains(typeof(List<ChatMessage>), protocol.Sends);
        Assert.Contains(typeof(ChatMessage), protocol.Sends);
        Assert.Contains(typeof(TurnToken), protocol.Sends);
        Assert.Contains(typeof(ResetChatSignal), protocol.Sends);
    }
}
