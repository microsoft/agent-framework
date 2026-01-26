// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Workflows.UnitTests;

public class AgentEventsTests
{
    /// <summary>
    /// Regression test for https://github.com/microsoft/agent-framework/issues/2938
    /// Verifies that WorkflowOutputEvent is triggered for agent workflows built with
    /// WorkflowBuilder directly (without using AgentWorkflowBuilder helpers).
    /// </summary>
    [Fact]
    public async Task WorkflowBuilder_WithAgents_EmitsWorkflowOutputEventAsync()
    {
        // Arrange - Build workflow using WorkflowBuilder directly (not AgentWorkflowBuilder.BuildSequential)
        AIAgent agent1 = new TestEchoAgent("agent1");
        AIAgent agent2 = new TestEchoAgent("agent2");

        Workflow workflow = new WorkflowBuilder(agent1)
            .AddEdge(agent1, agent2)
            .Build();

        // Act
        await using StreamingRun run = await InProcessExecution.StreamAsync(workflow, new List<ChatMessage> { new(ChatRole.User, "Hello") });
        await run.TrySendMessageAsync(new TurnToken(emitEvents: true));

        List<WorkflowOutputEvent> outputEvents = new();
        List<AgentResponseUpdateEvent> updateEvents = new();

        await foreach (WorkflowEvent evt in run.WatchStreamAsync())
        {
            if (evt is AgentResponseUpdateEvent updateEvt)
            {
                updateEvents.Add(updateEvt);
            }

            if (evt is WorkflowOutputEvent outputEvt)
            {
                outputEvents.Add(outputEvt);
            }
        }

        // Assert - AgentResponseUpdateEvent should now be a WorkflowOutputEvent
        Assert.NotEmpty(updateEvents);
        Assert.NotEmpty(outputEvents);
        // All update events should also be output events (since AgentResponseUpdateEvent now inherits from WorkflowOutputEvent)
        Assert.All(updateEvents, updateEvt => Assert.Contains(updateEvt, outputEvents));
    }

    /// <summary>
    /// Verifies that AgentResponseUpdateEvent inherits from WorkflowOutputEvent.
    /// </summary>
    [Fact]
    public void AgentResponseUpdateEvent_IsWorkflowOutputEvent()
    {
        // Arrange
        AgentResponseUpdate update = new(ChatRole.Assistant, "test");

        // Act
        AgentResponseUpdateEvent evt = new("executor1", update);

        // Assert
        Assert.IsAssignableFrom<WorkflowOutputEvent>(evt);
        Assert.Equal("executor1", evt.ExecutorId);
        Assert.Same(update, evt.Update);
        Assert.Same(update, evt.Data);
    }

    /// <summary>
    /// Verifies that AgentResponseEvent inherits from WorkflowOutputEvent.
    /// </summary>
    [Fact]
    public void AgentResponseEvent_IsWorkflowOutputEvent()
    {
        // Arrange
        AgentResponse response = new(new List<ChatMessage> { new(ChatRole.Assistant, "test") });

        // Act
        AgentResponseEvent evt = new("executor1", response);

        // Assert
        Assert.IsAssignableFrom<WorkflowOutputEvent>(evt);
        Assert.Equal("executor1", evt.ExecutorId);
        Assert.Same(response, evt.Response);
        Assert.Same(response, evt.Data);
    }
}
