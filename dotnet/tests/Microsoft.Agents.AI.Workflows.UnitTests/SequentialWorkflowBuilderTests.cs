// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Runtime.CompilerServices;
using System.Threading;
using System.Threading.Tasks;
using FluentAssertions;
using Microsoft.Agents.AI.Workflows.UnitTests.Futures;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Workflows.UnitTests;

public class SequentialWorkflowBuilderTests
{
    [Fact]
    public void Test_SequentialWorkflowBuilder_InvalidArguments_Throws()
    {
        Assert.Throws<ArgumentNullException>("agents", () => new SequentialWorkflowBuilder(null!));
        Assert.Throws<ArgumentException>("agents", () => new SequentialWorkflowBuilder().Build());

        Assert.Throws<ArgumentNullException>("agents", () => AgentWorkflowBuilder.BuildSequential(workflowName: null!, null!));
        Assert.Throws<ArgumentException>("agents", () => AgentWorkflowBuilder.BuildSequential());
        Assert.Throws<ArgumentNullException>("agents", () => AgentWorkflowBuilder.CreateSequentialBuilderWith(null!));
    }

    [Theory]
    [InlineData(1)]
    [InlineData(2)]
    [InlineData(3)]
    [InlineData(4)]
    [InlineData(5)]
    public async Task Test_SequentialWorkflowBuilder_AgentsRunInOrderAsync(int numAgents)
    {
        var workflow = new SequentialWorkflowBuilder(
            from i in Enumerable.Range(1, numAgents)
            select new OrchestrationTestHelpers.DoubleEchoAgent($"agent{i}"))
            .Build();

        for (int iter = 0; iter < 3; iter++)
        {
            const string UserInput = "abc";
            (string updateText, List<ChatMessage>? result, _, _) =
                await OrchestrationTestHelpers.RunWorkflowAsync(workflow, [new ChatMessage(ChatRole.User, UserInput)]);

            Assert.NotNull(result);
            Assert.Equal(numAgents + 1, result.Count);

            Assert.Equal(ChatRole.User, result[0].Role);
            Assert.Null(result[0].AuthorName);
            Assert.Equal(UserInput, result[0].Text);

            string[] texts = new string[numAgents + 1];
            texts[0] = UserInput;
            string expectedTotal = string.Empty;
            for (int i = 1; i < numAgents + 1; i++)
            {
                string id = $"agent{((i - 1) % numAgents) + 1}";
                texts[i] = $"{id}{Double(string.Concat(texts.Take(i)))}";
                Assert.Equal(ChatRole.Assistant, result[i].Role);
                Assert.Equal(id, result[i].AuthorName);
                Assert.Equal(texts[i], result[i].Text);
                expectedTotal += texts[i];
            }

            Assert.Equal(expectedTotal, updateText);
            Assert.Equal(UserInput + expectedTotal, string.Concat(result));

            static string Double(string s) => s + s;
        }
    }

    [Fact]
    public async Task Test_SequentialWorkflowBuilder_DefaultNextAgentReceivesFullConversationAsync()
    {
        CapturingAgent first = new("agent1", "step-one");
        CapturingAgent second = new("agent2", "step-two");

        Workflow workflow = new SequentialWorkflowBuilder(first, second).Build();

        _ = await OrchestrationTestHelpers.RunWorkflowAsync(workflow, [new ChatMessage(ChatRole.User, "start")]);

        second.MessagesSeen.Should().NotBeNull();
        second.MessagesSeen.Should().HaveCount(2);
        second.MessagesSeen![0].Role.Should().Be(ChatRole.User);
        second.MessagesSeen[0].Text.Should().Be("start");
        second.MessagesSeen[1].Role.Should().Be(ChatRole.User);
        second.MessagesSeen[1].Text.Should().Be("step-one");
    }

    [Fact]
    public async Task Test_SequentialWorkflowBuilder_WithChainOnlyAgentResponses_NextAgentReceivesOnlyPreviousOutputAsync()
    {
        CapturingAgent first = new("agent1", "step-one");
        CapturingAgent second = new("agent2", "step-two");

        Workflow workflow = new SequentialWorkflowBuilder(first, second)
            .WithChainOnlyAgentResponses()
            .Build();

        _ = await OrchestrationTestHelpers.RunWorkflowAsync(workflow, [new ChatMessage(ChatRole.User, "start")]);

        second.MessagesSeen.Should().NotBeNull();
        second.MessagesSeen.Should().ContainSingle();
        second.MessagesSeen![0].Role.Should().Be(ChatRole.User);
        second.MessagesSeen[0].Text.Should().Be("step-one");
    }

    [Fact]
    public void Test_SequentialWorkflowBuilder_DefaultDesignationsMatchSpec()
    {
        Workflow workflow = new SequentialWorkflowBuilder(
            new OrchestrationTestHelpers.DoubleEchoAgent("agent1"),
            new OrchestrationTestHelpers.DoubleEchoAgent("agent2"),
            new OrchestrationTestHelpers.DoubleEchoAgent("agent3"))
            .Build();

        Dictionary<string, HashSet<OutputTag>> designations = workflow.OutputExecutors;
        designations.Where(kvp => kvp.Value.Count == 0)
            .Should().ContainSingle("OutputMessagesExecutor is the sole terminal output by default");
        designations.Where(kvp => kvp.Value.Contains(OutputTag.Intermediate))
            .Should().HaveCount(3, "every pipeline agent is designated intermediate by default");
    }

    [Fact]
    public void Test_SequentialWorkflowBuilder_ExplicitDesignationsReplaceDefaults()
    {
        OrchestrationTestHelpers.DoubleEchoAgent a1 = new("agent1");
        OrchestrationTestHelpers.DoubleEchoAgent a2 = new("agent2");
        OrchestrationTestHelpers.DoubleEchoAgent a3 = new("agent3");

        Workflow workflow = new SequentialWorkflowBuilder(a1, a2, a3)
            .WithOutputFrom(a1)
            .WithIntermediateOutputFrom([a2])
            .Build();

        Dictionary<string, HashSet<OutputTag>> designations = workflow.OutputExecutors;

        designations.Should().HaveCount(2,
            "only the two explicitly-designated agents land on the inner builder; the end default is suppressed");
        designations.Values.Where(tags => tags.Count == 0)
            .Should().ContainSingle("agent1 is the only terminal designation");
        designations.Values.Where(tags => tags.Contains(OutputTag.Intermediate))
            .Should().ContainSingle("agent2 is the only intermediate designation");
    }

    [Fact]
    public void Test_SequentialWorkflowBuilder_DesignationForNonParticipantThrows()
    {
        OrchestrationTestHelpers.DoubleEchoAgent participant = new("p1");
        OrchestrationTestHelpers.DoubleEchoAgent stranger = new("stranger");

        SequentialWorkflowBuilder builder = new SequentialWorkflowBuilder(participant)
            .WithIntermediateOutputFrom([stranger]);

        Action build = () => builder.Build();
        build.Should().Throw<InvalidOperationException>().WithMessage("*stranger*");
    }

    [Fact]
    public void Test_SequentialWorkflowBuilder_WithNamePropagatesToWorkflow()
    {
        Workflow workflow = new SequentialWorkflowBuilder(new OrchestrationTestHelpers.DoubleEchoAgent("agent1"))
            .WithName("named-sequential")
            .Build();

        workflow.Name.Should().Be("named-sequential");
    }

    [Fact]
    public void Test_SequentialWorkflowBuilder_WithDescriptionPropagatesToWorkflow()
    {
        Workflow workflow = new SequentialWorkflowBuilder(new OrchestrationTestHelpers.DoubleEchoAgent("agent1"))
            .WithDescription("describes the sequential pipeline")
            .Build();

        workflow.Description.Should().Be("describes the sequential pipeline");
    }

    private sealed class CapturingAgent(string name, string responseText) : AIAgent
    {
        public List<ChatMessage>? MessagesSeen { get; private set; }

        public override string Name => name;

        protected override ValueTask<AgentSession> CreateSessionCoreAsync(CancellationToken cancellationToken = default)
            => new(new CapturingAgentSession());

        protected override ValueTask<AgentSession> DeserializeSessionCoreAsync(System.Text.Json.JsonElement serializedState, System.Text.Json.JsonSerializerOptions? jsonSerializerOptions = null, CancellationToken cancellationToken = default)
            => new(new CapturingAgentSession());

        protected override ValueTask<System.Text.Json.JsonElement> SerializeSessionCoreAsync(AgentSession session, System.Text.Json.JsonSerializerOptions? jsonSerializerOptions = null, CancellationToken cancellationToken = default)
            => default;

        protected override Task<AgentResponse> RunCoreAsync(
            IEnumerable<ChatMessage> messages,
            AgentSession? session = null,
            AgentRunOptions? options = null,
            CancellationToken cancellationToken = default)
        {
            this.MessagesSeen = messages.ToList();
            return Task.FromResult(new AgentResponse(new ChatMessage(ChatRole.Assistant, responseText)));
        }

        protected override async IAsyncEnumerable<AgentResponseUpdate> RunCoreStreamingAsync(
            IEnumerable<ChatMessage> messages,
            AgentSession? session = null,
            AgentRunOptions? options = null,
            [EnumeratorCancellation] CancellationToken cancellationToken = default)
        {
            this.MessagesSeen = messages.ToList();
            await Task.Yield();

            string messageId = Guid.NewGuid().ToString("N");
            yield return new AgentResponseUpdate(ChatRole.Assistant, responseText)
            {
                AuthorName = this.Name,
                MessageId = messageId,
            };
        }

        private sealed class CapturingAgentSession() : AgentSession;
    }

    [Collection(FuturesSerialCollection.Name)]
    public class AsAgentForwarding
    {
        [Fact]
        public async Task Test_SequentialWorkflowBuilder_AsAgent_OnlyTerminalDesignationSurfacesAsync()
        {
            using FuturesScope _ = new(enabled: true);

            OrchestrationTestHelpers.DoubleEchoAgent agent1 = new("agent1");
            OrchestrationTestHelpers.DoubleEchoAgent agent2 = new("agent2");
            OrchestrationTestHelpers.DoubleEchoAgent agent3 = new("agent3");

            // Explicitly designate ONLY the last agent — defaults (which would tag every agent
            // intermediate) are suppressed, so under Futures-on, agent1/agent2 produce no
            // AgentResponse(Update)Events and nothing of theirs reaches the AsAgent stream.
            Workflow workflow = new SequentialWorkflowBuilder(agent1, agent2, agent3)
                .WithOutputFrom(agent3)
                .Build();

            List<AgentResponseUpdate> updates = await workflow
                .AsAIAgent("WorkflowAgent")
                .RunStreamingAsync(new ChatMessage(ChatRole.User, "abc"))
                .ToListAsync();

            // Filter by AuthorName — distinguishes which agent originated each update
            // (text-content checks are unreliable because agent3 echoes earlier agents' markers
            // as part of the cumulative pipeline payload).
            HashSet<string> authoredBy = updates
                .Select(u => u.AuthorName)
                .Where(n => !string.IsNullOrEmpty(n))
                .Select(n => n!)
                .ToHashSet();

            authoredBy.Should().Contain("agent3", "the terminal agent must surface");
            authoredBy.Should().NotContain("agent1",
                "the intermediate agent must not surface when only the terminal is designated");
            authoredBy.Should().NotContain("agent2",
                "the intermediate agent must not surface when only the terminal is designated");
        }
    }
}
