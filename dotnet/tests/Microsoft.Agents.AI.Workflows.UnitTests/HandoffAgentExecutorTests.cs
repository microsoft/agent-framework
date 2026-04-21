// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Runtime.CompilerServices;
using System.Threading;
using System.Threading.Tasks;
using FluentAssertions;
using Microsoft.Agents.AI.Workflows.Checkpointing;
using Microsoft.Agents.AI.Workflows.Execution;
using Microsoft.Agents.AI.Workflows.InProc;
using Microsoft.Agents.AI.Workflows.Sample;
using Microsoft.Agents.AI.Workflows.Specialized;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Workflows.UnitTests;

public class HandoffAgentExecutorTests : AIAgentHostingExecutorTestsBase
{
    private static async ValueTask<TestRunContext> PrepareHandoffSharedStateAsync(TestRunContext? runContext = null, IEnumerable<ChatMessage>? messages = null)
    {
        runContext ??= new();

        HandoffSharedState sharedState = new();

        if (messages != null)
        {
            sharedState.Conversation.AddMessages(messages);
        }

        await runContext.BindWorkflowContext(nameof(HandoffStartExecutor))
                        .QueueStateUpdateAsync(HandoffConstants.HandoffSharedStateKey,
                                               sharedState,
                                               HandoffConstants.HandoffSharedStateScope);

        await runContext.StateManager.PublishUpdatesAsync(null);

        return runContext;
    }

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
        TestRunContext testContext = await PrepareHandoffSharedStateAsync();
        TestReplayAgent agent = new(TestMessages, TestAgentId, TestAgentName);

        HandoffAgentExecutorOptions options = new("",
                                                  emitAgentResponseEvents: false,
                                                  emitAgentResponseUpdateEvents: executorSetting,
                                                  HandoffToolCallFilteringBehavior.None);

        HandoffAgentExecutor executor = new(agent, [], options);
        testContext.ConfigureExecutor(executor);

        // Act
        HandoffState message = new(new(turnSetting), null, null);
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
        TestRunContext testContext = await PrepareHandoffSharedStateAsync();
        TestReplayAgent agent = new(TestMessages, TestAgentId, TestAgentName);

        HandoffAgentExecutorOptions options = new("",
                                                  emitAgentResponseEvents: executorSetting,
                                                  emitAgentResponseUpdateEvents: false,
                                                  HandoffToolCallFilteringBehavior.None);

        HandoffAgentExecutor executor = new(agent, [], options);
        testContext.ConfigureExecutor(executor);

        // Act
        HandoffState message = new(new(false), null, null);
        await executor.HandleAsync(message, testContext.BindWorkflowContext(executor.Id));

        // Assert
        AgentResponseEvent[] updates = testContext.Events.OfType<AgentResponseEvent>().ToArray();
        CheckResponseEventsAgainstTestMessages(updates, expectingResponse: executorSetting, agent.GetDescriptiveId());
    }

    [Fact]
    public async Task Test_HandoffAgentExecutor_ComposesWithHITLSubworkflowAsync()
    {
        // Arrange
        TestRunContext testContext = await PrepareHandoffSharedStateAsync();

        SendsRequestExecutor challengeSender = new();
        Workflow subworkflow = new WorkflowBuilder(challengeSender)
                                   .AddExternalRequest<Challenge, Response>(challengeSender, "SendChallengeToUser")
                                   .WithOutputFrom(challengeSender)
                                   .Build();

        InProcessExecutionEnvironment environment = InProcessExecution.Lockstep.WithCheckpointing(CheckpointManager.CreateInMemory());
        AIAgent subworkflowAgent = subworkflow.AsAIAgent(includeWorkflowOutputsInResponse: true, name: "Subworkflow", executionEnvironment: environment);
        HandoffAgentExecutorOptions options = new("",
                                                  emitAgentResponseEvents: true,
                                                  emitAgentResponseUpdateEvents: true,
                                                  HandoffToolCallFilteringBehavior.None);

        HandoffAgentExecutor executor = new(subworkflowAgent, [], options);
        Workflow fakeWorkflow = new(executor.Id) { ExecutorBindings = { { executor.Id, executor } } };
        EdgeMap map = new(testContext, fakeWorkflow, null);

        testContext.ConfigureExecutor(executor, map);

        // Validate that our test assumptions hold
        string functionCallPortId = $"{HandoffAgentExecutor.IdFor(subworkflowAgent)}_FunctionCall";
        map.TryGetResponsePortExecutorId(functionCallPortId, out string? responsePortExecutorId).Should().BeTrue();
        responsePortExecutorId.Should().Be(executor.Id);

        // Act
        HandoffState message = new(new(false), null, null);
        await executor.HandleAsync(message, testContext.BindWorkflowContext(executor.Id));

        await testContext.StateManager.PublishUpdatesAsync(null);

        // Assert
        testContext.ExternalRequests.Should().HaveCount(1)
                                .And.ContainSingle(request => request.IsDataOfType<FunctionCallContent>());

        FunctionCallContent functionCallContent = testContext.ExternalRequests.Single().Data.As<FunctionCallContent>()!;
        object? requestData = functionCallContent.Arguments!["data"];

        Challenge? challenge = null;
        if (requestData is PortableValue pv)
        {
            challenge = pv.As<Challenge>();
        }
        else
        {
            challenge = requestData as Challenge;
        }

        if (challenge is null)
        {
            Assert.Fail($"Expected request data to be of type {typeof(Challenge).FullName}, but was {requestData?.GetType().FullName ?? "null"}");
            return; // Unreachable, but analysis cannot infer that Debug.Fail will throw/exit, and UnreachableException is not available on net472
        }

        // Act 2
        string challengeResponse = new(challenge.Value.Reverse().ToArray());
        FunctionResultContent responseContent = new(functionCallContent.CallId, new Response(challengeResponse));

        RequestPortInfo requestPortInfo = new(new(typeof(Challenge)), new(typeof(Response)), functionCallPortId);
        string requestId = $"{functionCallPortId.Length}:{functionCallPortId}:{functionCallContent.CallId}";
        DeliveryMapping? mapping = await map.PrepareDeliveryForResponseAsync(new(requestPortInfo, requestId, new(responseContent)));

        mapping!.Deliveries.Should().HaveCount(1);

        MessageDelivery delivery = mapping!.Deliveries.Single();

        object? result = await executor.ExecuteCoreAsync(delivery.Envelope.Message,
                                                         delivery.Envelope.MessageType,
                                                         testContext.BindWorkflowContext(executor.Id));
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

        TestRunContext runContext = await PrepareHandoffSharedStateAsync();
        IWorkflowContext testContext = runContext.BindWorkflowContext(executor.Id);
        HandoffState state = new(new(false), null);

        // Act / Assert
        Func<Task> runStreamingAsync = async () => await executor.HandleAsync(state, testContext);
        await runStreamingAsync.Should().NotThrowAsync();
    }
}

internal sealed record Challenge(string Value);
internal sealed record Response(string Value);

[SendsMessage(typeof(Challenge))]
internal sealed partial class SendsRequestExecutor(string? id = null) : ChatProtocolExecutor(id ?? nameof(SendsRequestExecutor), s_chatOptions)
{
    internal const string ChallengeString = "{C7A762AE-7DAA-4D9C-A647-E64E6DBC35AE}";
    private static string ResponseKey { get; } = new(ChallengeString.Reverse().ToArray());

    private static readonly ChatProtocolExecutorOptions s_chatOptions = new()
    {
        AutoSendTurnToken = false
    };

    protected override ValueTask TakeTurnAsync(List<ChatMessage> messages, IWorkflowContext context, bool? emitEvents, CancellationToken cancellationToken = default)
        => context.SendMessageAsync(new Challenge(ChallengeString), cancellationToken);

    [MessageHandler]
    public async ValueTask HandleChallengeResponseAsync(Response response, IWorkflowContext context, CancellationToken cancellationToken = default)
    {
        if (response.Value != ResponseKey)
        {
            throw new InvalidOperationException($"Incorrect response received. Expected '{ResponseKey}' but got '{response.Value}'");
        }

        await context.SendMessageAsync(new ChatMessage(ChatRole.Assistant, "Correct response."), cancellationToken)
                     .ConfigureAwait(false);

        await context.SendMessageAsync(new TurnToken(false), cancellationToken).ConfigureAwait(false);
    }
}

internal sealed class OptionValidatingChatClient(string baseInstructions, string handoffInstructions, AITool baseTool) : IChatClient
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
