// Copyright (c) Microsoft. All rights reserved.

using System.Linq;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Workflows.Specialized;

namespace Microsoft.Agents.AI.Workflows.UnitTests;

public class HandoffAgentExecutorTests : AIAgentHostingExecutorTestsBase
{
    [Theory]
    [InlineData(null, null)]
    [InlineData(null, true)]
    [InlineData(null, false)]
    [InlineData(true, null)]
    [InlineData(true, true)]
    [InlineData(true, false)]
    [InlineData(false, null)]
    [InlineData(false, true)]
    [InlineData(false, false)]
    public async Task Test_HandoffAgentExecutor_EmitsStreamingUpdatesIFFConfiguredAsync(bool? executorSetting, bool? turnSetting)
    {
        // Arrange
        TestRunContext testContext = new();
        TestReplayAgent agent = new(TestMessages, TestAgentId, TestAgentName);

        HandoffAgentExecutorOptions options = new("",
                                                  emitAgentResponseEvents: false,
                                                  emitAgentResponseUpdateEvents: executorSetting,
                                                  HandoffToolCallFilteringBehavior.None);

        HandoffAgentExecutor executor = new(agent, options);
        testContext.ConfigureExecutor(executor);

        // Act
        HandoffState message = new(new(turnSetting), null, []);
        await executor.HandleAsync(message, testContext.BindWorkflowContext(executor.Id));

        // Assert
        bool expectingStreamingUpdates = turnSetting ?? executorSetting ?? false;

        AgentResponseUpdateEvent[] updates = testContext.Events.OfType<AgentResponseUpdateEvent>().ToArray();
        CheckResponseUpdateEventsAgainstTestMessages(updates, expectingStreamingUpdates, agent.GetDescriptiveId());
    }

    [Theory]
    [InlineData(true)]
    [InlineData(false)]
    public async Task Test_HandoffAgentExecutor_EmitsResponseIFFConfiguredAsync(bool executorSetting)
    {
        // Arrange
        TestRunContext testContext = new();
        TestReplayAgent agent = new(TestMessages, TestAgentId, TestAgentName);

        HandoffAgentExecutorOptions options = new("",
                                                  emitAgentResponseEvents: executorSetting,
                                                  emitAgentResponseUpdateEvents: false,
                                                  HandoffToolCallFilteringBehavior.None);

        HandoffAgentExecutor executor = new(agent, options);
        testContext.ConfigureExecutor(executor);

        // Act
        HandoffState message = new(new(false), null, []);
        await executor.HandleAsync(message, testContext.BindWorkflowContext(executor.Id));

        // Assert
        AgentResponseEvent[] updates = testContext.Events.OfType<AgentResponseEvent>().ToArray();
        CheckResponseEventsAgainstTestMessages(updates, expectingResponse: executorSetting, agent.GetDescriptiveId());
    }
}
