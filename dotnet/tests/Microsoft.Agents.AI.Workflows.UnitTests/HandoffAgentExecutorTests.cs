// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Runtime.CompilerServices;
using System.Threading;
using System.Threading.Tasks;
using FluentAssertions;
using Microsoft.Agents.AI.Workflows.Specialized;
using Microsoft.Extensions.AI;

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

        HandoffAgentExecutor executor = new(agent, [], options);
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

        HandoffAgentExecutor executor = new(agent, [], options);
        testContext.ConfigureExecutor(executor);

        // Act
        HandoffState message = new(new(false), null, []);
        await executor.HandleAsync(message, testContext.BindWorkflowContext(executor.Id));

        // Assert
        AgentResponseEvent[] updates = testContext.Events.OfType<AgentResponseEvent>().ToArray();
        CheckResponseEventsAgainstTestMessages(updates, expectingResponse: executorSetting, agent.GetDescriptiveId());
    }

    [Fact]
    public async Task Test_HandoffAgentExecutor_PreservesExistingInstructionsAndToolsAsync()
    {
        // Arrange
        const string BaseInstructions = "BaseInstructions";
        const string HandoffInstructions = "HandoffInstructions";

        AITool someTool = AIFunctionFactory.CreateDeclaration("BaseTool", null, AIFunctionFactory.Create(() => { }).JsonSchema);

        OptionValidatingChatClient chatClient = new(BaseInstructions, HandoffInstructions, someTool);
        AIAgent handoffAgent = chatClient.AsAIAgent(BaseInstructions, tools: [someTool]);
        AIAgent targetAgent = new TestEchoAgent();

        HandoffAgentExecutorOptions options = new(HandoffInstructions, false, null, HandoffToolCallFilteringBehavior.None);
        HandoffTarget handoff = new(targetAgent);
        HandoffAgentExecutor executor = new(handoffAgent, [handoff], options);

        TestWorkflowContext testContext = new(executor.Id);
        HandoffState state = new(new(false), null, [], null);

        // Act / Assert
        Func<Task> runStreamingAsync = async () => await executor.HandleAsync(state, testContext);
        await runStreamingAsync.Should().NotThrowAsync();
    }

    private sealed class OptionValidatingChatClient(string baseInstructions, string handoffInstructions, AITool baseTool) : IChatClient
    {
        public void Dispose()
        {
        }

        private void CheckOptions(ChatOptions? options)
        {
            options.Should().NotBeNull();

            options.Instructions.Should().NotBeNullOrEmpty("Handoff orchestration should preserve and augment instructions.")
                                     .And.Contain(baseInstructions, because: "Handoff orchestration should preserve existing instructions.")
                                     .And.Contain(handoffInstructions, because: "Handoff orchestration should inject handoff instructions.");

            options.Tools.Should().NotBeNullOrEmpty("Handoff orchestration should preserve and augment tools.")
                                  .And.Contain(tool => tool.Name == baseTool.Name, "Handoff orchestration should preserve existing tools.")
                                  .And.Contain(tool => tool.Name.StartsWith(HandoffWorkflowBuilder.FunctionPrefix, StringComparison.Ordinal),
                                               because: "Handoff orchestration should inject handoff tools.");
        }

        private List<ChatMessage> ResponseMessages =>
            [
                new ChatMessage(ChatRole.Assistant, "Ok")
                {
                    MessageId = Guid.NewGuid().ToString(),
                    AuthorName = nameof(OptionValidatingChatClient)
                }
            ];

        public Task<ChatResponse> GetResponseAsync(IEnumerable<ChatMessage> messages, ChatOptions? options = null, CancellationToken cancellationToken = default)
        {
            this.CheckOptions(options);

            ChatResponse response = new(this.ResponseMessages)
            {
                ResponseId = Guid.NewGuid().ToString("N"),
                CreatedAt = DateTimeOffset.Now
            };

            return Task.FromResult(response);
        }

        public object? GetService(Type serviceType, object? serviceKey = null)
        {
            if (serviceType == typeof(OptionValidatingChatClient))
            {
                return this;
            }

            return null;
        }

        public async IAsyncEnumerable<ChatResponseUpdate> GetStreamingResponseAsync(IEnumerable<ChatMessage> messages, ChatOptions? options = null, [EnumeratorCancellation] CancellationToken cancellationToken = default)
        {
            this.CheckOptions(options);

            string responseId = Guid.NewGuid().ToString("N");
            foreach (ChatMessage message in this.ResponseMessages)
            {
                yield return new(message.Role, message.Contents)
                {
                    ResponseId = responseId,
                    MessageId = message.MessageId,
                    CreatedAt = DateTimeOffset.Now
                };
            }
        }
    }
}
