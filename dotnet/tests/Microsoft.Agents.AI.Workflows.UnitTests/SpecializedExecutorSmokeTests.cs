// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Workflows.Checkpointing;
using Microsoft.Agents.AI.Workflows.Execution;
using Microsoft.Agents.AI.Workflows.Specialized;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Workflows.UnitTests;

public class SpecializedExecutorSmokeTests
{
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

        List<ChatMessage> expected = TestReplayAgent.ToChatMessages(MessageStrings);

        TestReplayAgent agent = new(expected);
        AIAgentHostExecutor host = new(agent, new());

        TestWorkflowContext collectingContext = new(host.Id);

        await host.TakeTurnAsync(new TurnToken(emitEvents: true), collectingContext);

        // The first empty message is skipped.
        Assert.Equal(MessageStrings.Length - 1, collectingContext.Updates.Count);

        for (int i = 1; i < MessageStrings.Length; i++)
        {
            string expectedText = MessageStrings[i];
            ChatMessage collected = collectingContext.Updates[i - 1];

            Assert.Equal(expectedText, collected.Text);
        }
    }

    [Fact]
    public async Task Test_AIAgent_ExecutorId_Use_Agent_NameAsync()
    {
        const string AgentAName = "TestAgentAName";
        const string AgentBName = "TestAgentBName";
        TestReplayAgent agentA = new(name: AgentAName);
        TestReplayAgent agentB = new(name: AgentBName);
        var workflow = new WorkflowBuilder(agentA).AddEdge(agentA, agentB).Build();
        var definition = workflow.ToWorkflowInfo();

        // Verify that the agent host executor registration IDs in the workflow definition
        // match the agent names when agent names are provided.
        // The property DisplayName falls back to using the agent ID when Name is not set.
        Assert.Contains(AgentAName, agentA.GetDescriptiveId());
        Assert.Contains(AgentBName, agentB.GetDescriptiveId());
        Assert.Equal(agentA.GetDescriptiveId(), definition.Executors[agentA.GetDescriptiveId()].ExecutorId);
        Assert.Equal(agentB.GetDescriptiveId(), definition.Executors[agentB.GetDescriptiveId()].ExecutorId);

        // This will create an instance of the start agent and verify that the ID
        // of the executor instance matches the ID of the registration.
        var protocolDescriptor = await workflow.DescribeProtocolAsync();
        Assert.Contains(typeof(ChatMessage), protocolDescriptor.Accepts);
    }

    [Fact]
    public async Task Test_AIAgent_ExecutorId_Use_Agent_ID_When_Name_Not_ProvidedAsync()
    {
        TestReplayAgent agentA = new();
        TestReplayAgent agentB = new();
        var workflow = new WorkflowBuilder(agentA).AddEdge(agentA, agentB).Build();
        var definition = workflow.ToWorkflowInfo();

        // Verify that the agent host executor registration IDs in the workflow definition
        // match the agent IDs when agent names are not provided.
        // The property DisplayName falls back to using the agent ID when Name is not set.
        Assert.Contains(agentA.Id, agentA.GetDescriptiveId());
        Assert.Contains(agentB.Id, agentB.GetDescriptiveId());
        Assert.Equal(agentA.GetDescriptiveId(), definition.Executors[agentA.GetDescriptiveId()].ExecutorId);
        Assert.Equal(agentB.GetDescriptiveId(), definition.Executors[agentB.GetDescriptiveId()].ExecutorId);

        // This will create an instance of the start agent and verify that the ID
        // of the executor instance matches the ID of the registration.
        var protocolDescriptor = await workflow.DescribeProtocolAsync();
        Assert.Contains(typeof(ChatMessage), protocolDescriptor.Accepts);
    }
}
