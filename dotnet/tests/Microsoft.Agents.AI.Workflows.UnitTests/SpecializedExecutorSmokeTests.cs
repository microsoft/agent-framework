// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Runtime.CompilerServices;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using FluentAssertions;
using Microsoft.Agents.AI.Workflows.Checkpointing;
using Microsoft.Agents.AI.Workflows.Execution;
using Microsoft.Agents.AI.Workflows.Specialized;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Workflows.UnitTests;

public class SpecializedExecutorSmokeTests
{
    public class TestAIAgent(List<ChatMessage>? messages = null, string? id = null, string? name = null) : AIAgent
    {
        protected override string? IdCore => id;
        public override string? Name => name;

        public static List<ChatMessage> ToChatMessages(params string[] messages)
        {
            List<ChatMessage> result = messages.Select(ToMessage).ToList();

            static ChatMessage ToMessage(string text)
            {
                if (string.IsNullOrEmpty(text))
                {
                    return new ChatMessage(ChatRole.Assistant, "") { MessageId = "" };
                }

                string[] splits = text.Split(' ');
                for (int i = 0; i < splits.Length - 1; i++)
                {
                    splits[i] += ' ';
                }

                List<AIContent> contents = splits.Select<string, AIContent>(text => new TextContent(text) { RawRepresentation = text }).ToList();
                return new(ChatRole.Assistant, contents)
                {
                    MessageId = Guid.NewGuid().ToString("N"),
                    RawRepresentation = text,
                    CreatedAt = DateTime.UtcNow,
                };
            }

            return result;
        }

        public override AgentThread GetNewThread()
            => new TestAgentThread();

        public override AgentThread DeserializeThread(JsonElement serializedThread, JsonSerializerOptions? jsonSerializerOptions = null)
            => new TestAgentThread();

        public static TestAIAgent FromStrings(params string[] messages) =>
            new(ToChatMessages(messages));

        public List<ChatMessage> Messages { get; } = Validate(messages) ?? [];

        public override Task<AgentRunResponse> RunAsync(IEnumerable<ChatMessage> messages, AgentThread? thread = null, AgentRunOptions? options = null, CancellationToken cancellationToken = default) =>
            Task.FromResult(new AgentRunResponse(this.Messages)
            {
                AgentId = this.Id,
                ResponseId = Guid.NewGuid().ToString("N")
            });

        public override async IAsyncEnumerable<AgentRunResponseUpdate> RunStreamingAsync(IEnumerable<ChatMessage> messages, AgentThread? thread = null, AgentRunOptions? options = null, [EnumeratorCancellation] CancellationToken cancellationToken = default)
        {
            string responseId = Guid.NewGuid().ToString("N");
            foreach (ChatMessage message in this.Messages)
            {
                foreach (AIContent content in message.Contents)
                {
                    yield return new AgentRunResponseUpdate()
                    {
                        AgentId = this.Id,
                        MessageId = message.MessageId,
                        ResponseId = responseId,
                        Contents = [content],
                        Role = message.Role,
                    };
                }
            }
        }

        private static List<ChatMessage>? Validate(List<ChatMessage>? candidateMessages)
        {
            string? currentMessageId = null;

            if (candidateMessages is not null)
            {
                foreach (ChatMessage message in candidateMessages)
                {
                    if (currentMessageId is null)
                    {
                        currentMessageId = message.MessageId;
                    }
                    else if (currentMessageId == message.MessageId)
                    {
                        throw new ArgumentException("Duplicate consecutive message ids");
                    }
                }
            }

            return candidateMessages;
        }
    }

    public sealed class TestAgentThread() : InMemoryAgentThread();

    internal sealed class TestWorkflowContext(string executorId, bool concurrentRunsEnabled = false) : IWorkflowContext
    {
        private readonly StateManager _stateManager = new();

        public List<ChatMessage> Updates { get; } = [];

        public ValueTask AddEventAsync(WorkflowEvent workflowEvent, CancellationToken cancellationToken = default) =>
            default;

        public ValueTask YieldOutputAsync(object output, CancellationToken cancellationToken = default) =>
            default;

        public ValueTask RequestHaltAsync() =>
            default;

        public ValueTask QueueClearScopeAsync(string? scopeName = null, CancellationToken cancellationToken = default)
            => this._stateManager.ClearStateAsync(new ScopeId(executorId, scopeName));

        public ValueTask QueueStateUpdateAsync<T>(string key, T? value, string? scopeName = null, CancellationToken cancellationToken = default)
            => value is null
             ? this._stateManager.ClearStateAsync(new ScopeId(executorId, scopeName), key)
             : this._stateManager.WriteStateAsync(new ScopeId(executorId, scopeName), key, value);

        public ValueTask<T?> ReadStateAsync<T>(string key, string? scopeName = null, CancellationToken cancellationToken = default)
            => this._stateManager.ReadStateAsync<T>(new ScopeId(executorId, scopeName), key);

        public ValueTask<HashSet<string>> ReadStateKeysAsync(string? scopeName = null, CancellationToken cancellationToken = default)
            => this._stateManager.ReadKeysAsync(new ScopeId(executorId, scopeName));

        public ValueTask SendMessageAsync(object message, string? targetId = null, CancellationToken cancellationToken = default)
        {
            if (message is List<ChatMessage> messages)
            {
                this.Updates.AddRange(messages);
            }
            else if (message is ChatMessage chatMessage)
            {
                this.Updates.Add(chatMessage);
            }

            return default;
        }

        public async ValueTask<T> ReadOrInitStateAsync<T>(string key, Func<T> initialStateFactory, string? scopeName = null, CancellationToken cancellationToken = default)
        {
            return (await this.ReadStateAsync<T>(key, scopeName, cancellationToken).ConfigureAwait(false))
                ?? initialStateFactory();
        }

        public IReadOnlyDictionary<string, string>? TraceContext => null;

        public bool ConcurrentRunsEnabled => concurrentRunsEnabled;
    }

    [Fact]
    public async Task Test_AIAgentStreamingMessage_AggregationAsync()
    {
        string[] MessageStrings = [
            "",
            "Hello world!",
            "Lorem ipsum dolor sit amet, consectetur adipiscing elit.",
            "Quisque dignissim ante odio, at facilisis orci porta a. Duis mi augue, fringilla eu egestas a, pellentesque sed lacus."
        ];

        List<ChatMessage> expected = TestAIAgent.ToChatMessages(MessageStrings);

        TestAIAgent agent = new(expected);
        AIAgentHostExecutor host = new(agent);

        TestWorkflowContext collectingContext = new(host.Id);

        await host.TakeTurnAsync(new TurnToken(emitEvents: true), collectingContext);

        // The first empty message is skipped.
        collectingContext.Updates.Should().HaveCount(MessageStrings.Length - 1);

        for (int i = 1; i < MessageStrings.Length; i++)
        {
            string expectedText = MessageStrings[i];
            ChatMessage collected = collectingContext.Updates[i - 1];

            collected.Text.Should().Be(expectedText);
        }
    }

    [Fact]
    public async Task Test_AIAgent_ExecutorId_Use_Agent_NameAsync()
    {
        const string AgentAName = "TestAgentAName";
        const string AgentBName = "TestAgentBName";
        TestAIAgent agentA = new(name: AgentAName);
        TestAIAgent agentB = new(name: AgentBName);
        var workflow = new WorkflowBuilder(agentA).AddEdge(agentA, agentB).Build();
        var definition = workflow.ToWorkflowInfo();

        // Verify that the agent host executor registration IDs in the workflow definition
        // match the agent names when agent names are provided.
        // The property DisplayName falls back to using the agent ID when Name is not set.
        agentA.GetDescriptiveId().Should().Contain(AgentAName);
        agentB.GetDescriptiveId().Should().Contain(AgentBName);
        definition.Executors[agentA.GetDescriptiveId()].ExecutorId.Should().Be(agentA.GetDescriptiveId());
        definition.Executors[agentB.GetDescriptiveId()].ExecutorId.Should().Be(agentB.GetDescriptiveId());

        // This will create an instance of the start agent and verify that the ID
        // of the executor instance matches the ID of the registration.
        var protocolDescriptor = await workflow.DescribeProtocolAsync();
        protocolDescriptor.Accepts.Should().Contain(typeof(ChatMessage));
    }

    [Fact]
    public async Task Test_AIAgent_ExecutorId_Use_Agent_ID_When_Name_Not_ProvidedAsync()
    {
        TestAIAgent agentA = new();
        TestAIAgent agentB = new();
        var workflow = new WorkflowBuilder(agentA).AddEdge(agentA, agentB).Build();
        var definition = workflow.ToWorkflowInfo();

        // Verify that the agent host executor registration IDs in the workflow definition
        // use the agent's type name and first 8 characters of the ID when names are not provided.
        // The format is "{TypeName}_{first8charsOfId}" for readability in workflow visualizations.
        agentA.GetDescriptiveId().Should().Contain(nameof(TestAIAgent));
        agentB.GetDescriptiveId().Should().Contain(nameof(TestAIAgent));
        string agentAIdPrefix = agentA.Id.Length > 8 ? agentA.Id.Substring(0, 8) : agentA.Id;
        string agentBIdPrefix = agentB.Id.Length > 8 ? agentB.Id.Substring(0, 8) : agentB.Id;
        agentA.GetDescriptiveId().Should().Contain(agentAIdPrefix);
        agentB.GetDescriptiveId().Should().Contain(agentBIdPrefix);
        definition.Executors[agentA.GetDescriptiveId()].ExecutorId.Should().Be(agentA.GetDescriptiveId());
        definition.Executors[agentB.GetDescriptiveId()].ExecutorId.Should().Be(agentB.GetDescriptiveId());

        // This will create an instance of the start agent and verify that the ID
        // of the executor instance matches the ID of the registration.
        var protocolDescriptor = await workflow.DescribeProtocolAsync();
        protocolDescriptor.Accepts.Should().Contain(typeof(ChatMessage));
    }

    [Fact]
    public void Test_GetDescriptiveId_WithName_ReturnsNameWithGuidSuffix()
    {
        // Arrange
        const string AgentName = "MyPhysicist";
        TestAIAgent agent = new(name: AgentName);

        // Act
        string descriptiveId = agent.GetDescriptiveId();

        // Assert
        descriptiveId.Should().StartWith($"{AgentName}_");
        descriptiveId.Should().HaveLength(AgentName.Length + 1 + 8); // name + underscore + 8 chars
        string idPrefix = agent.Id.Length > 8 ? agent.Id.Substring(0, 8) : agent.Id;
        descriptiveId.Should().Contain(idPrefix);
    }

    [Fact]
    public void Test_GetDescriptiveId_WithoutName_ReturnsTypeNameWithGuidSuffix()
    {
        // Arrange
        TestAIAgent agent = new();

        // Act
        string descriptiveId = agent.GetDescriptiveId();

        // Assert
        descriptiveId.Should().StartWith($"{nameof(TestAIAgent)}_");
        descriptiveId.Should().HaveLength(nameof(TestAIAgent).Length + 1 + 8); // typename + underscore + 8 chars
        string idPrefix = agent.Id.Length > 8 ? agent.Id.Substring(0, 8) : agent.Id;
        descriptiveId.Should().Contain(idPrefix);
    }

    [Fact]
    public void Test_GetDescriptiveId_SanitizesInvalidCharacters()
    {
        // Arrange
        const string AgentName = "My Agent-Name!@#";
        TestAIAgent agent = new(name: AgentName);

        // Act
        string descriptiveId = agent.GetDescriptiveId();

        // Assert
        descriptiveId.Should().NotContain(" ");
        descriptiveId.Should().NotContain("-");
        descriptiveId.Should().NotContain("!");
        descriptiveId.Should().NotContain("@");
        descriptiveId.Should().NotContain("#");
        descriptiveId.Should().MatchRegex("^[A-Za-z0-9_]+$");
    }

    [Fact]
    public void Test_BindAsExecutor_WithCustomDescriptiveId_UsesProvidedId()
    {
        // Arrange
        TestAIAgent agent = new(name: "SomeAgent");
        const string CustomId = "MyCustomExecutorId";

        // Act
        ExecutorBinding binding = agent.BindAsExecutor(CustomId);

        // Assert
        binding.Id.Should().Be(CustomId);
    }

    [Fact]
    public void Test_BindAsExecutor_WithCustomDescriptiveId_PreservesAgentInBinding()
    {
        // Arrange
        TestAIAgent agent = new(name: "SomeAgent");
        const string CustomId = "MyCustomExecutorId";

        // Act
        AIAgentBinding binding = (AIAgentBinding)agent.BindAsExecutor(CustomId);

        // Assert
        binding.Agent.Should().BeSameAs(agent);
        binding.DescriptiveId.Should().Be(CustomId);
    }

    [Fact]
    public async Task Test_BindAsExecutor_WithCustomDescriptiveId_WorkflowVisualizationUsesCustomIdAsync()
    {
        // Arrange
        TestAIAgent agentA = new(name: "Physicist");
        TestAIAgent agentB = new(name: "Chemist");
        ExecutorBinding physicistExecutor = agentA.BindAsExecutor("Physicist");
        ExecutorBinding chemistExecutor = agentB.BindAsExecutor("Chemist");

        // Act
        var workflow = new WorkflowBuilder(physicistExecutor)
            .AddEdge(physicistExecutor, chemistExecutor)
            .Build();

        var mermaid = workflow.ToMermaidString();
        var dot = workflow.ToDotString();

        // Assert - visualization should use custom IDs, not GUIDs
        mermaid.Should().Contain("Physicist");
        mermaid.Should().Contain("Chemist");

        // Use bounds checking for Substring to avoid ArgumentOutOfRangeException
        string agentAIdPrefix = agentA.Id.Length > 8 ? agentA.Id.Substring(0, 8) : agentA.Id;
        string agentBIdPrefix = agentB.Id.Length > 8 ? agentB.Id.Substring(0, 8) : agentB.Id;
        mermaid.Should().NotContain(agentAIdPrefix); // Should not contain GUID suffix
        mermaid.Should().NotContain(agentBIdPrefix);

        dot.Should().Contain("Physicist");
        dot.Should().Contain("Chemist");

        // Verify workflow is still functional
        var protocolDescriptor = await workflow.DescribeProtocolAsync();
        protocolDescriptor.Accepts.Should().Contain(typeof(ChatMessage));
    }
}
