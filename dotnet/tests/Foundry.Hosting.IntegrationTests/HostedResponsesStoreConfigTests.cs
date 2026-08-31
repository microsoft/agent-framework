// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Threading.Tasks;
using Foundry.Hosting.IntegrationTests.Fixtures;
using Microsoft.Agents.AI;
using Microsoft.Extensions.AI;
using OpenAI.Responses;

#pragma warning disable OPENAI001 // Experimental Responses API surfaces

namespace Foundry.Hosting.IntegrationTests;

/// <summary>
/// Store and session semantics for a hosted Responses agent: <c>store=true</c> vs <c>store=false</c>,
/// <c>previous_response_id</c> and <c>conversation_id</c> forks, and multi-turn recall. Stored
/// hosted-agent responses are read through the per-agent endpoint client (the project-level client
/// returns 403 <c>session_not_accessible</c>).
/// </summary>
[Trait("Category", "FoundryHostedAgents")]
public sealed class HostedResponsesStoreConfigTests(HostedResponsesStoreConfigFixture fixture) : IClassFixture<HostedResponsesStoreConfigFixture>
{
    private readonly HostedResponsesStoreConfigFixture _fixture = fixture;

    [Fact]
    public async Task StoredTrue_Default_PersistsResponseInChainAsync()
    {
        // Arrange
        var agent = this._fixture.Agent;

        // Act
        var response = await agent.RunAsync("Reply with the word 'ack'.");

        // Assert
        Assert.False(string.IsNullOrWhiteSpace(response.Text));
        // Stored hosted-agent responses are readable only through the per-agent endpoint client.
        var fetched = await this._fixture.AgentOpenAIClient.GetProjectResponsesClient().GetResponseAsync(response.ResponseId!);
        Assert.NotNull(fetched.Value);
    }

    [Fact]
    public async Task StoredFalse_Baseline_DoesNotPersistResponseAsync()
    {
        // Arrange
        var agent = this._fixture.Agent;
        var options = new ChatClientAgentRunOptions(new ChatOptions
        {
            RawRepresentationFactory = _ => new CreateResponseOptions { StoredOutputEnabled = false }
        });

        // Act
        var response = await agent.RunAsync("Reply with the word 'pong'.", options: options);

        // Assert: response returned but the response id is not retrievable from the chain.
        Assert.False(string.IsNullOrWhiteSpace(response.Text));
        var responseId = response.ResponseId;
        Assert.False(string.IsNullOrWhiteSpace(responseId));

        // Attempting to fetch the response should fail because nothing was stored. Reads go through
        // the per-agent endpoint client (the project-level client returns 403 session_not_accessible).
        await Assert.ThrowsAnyAsync<Exception>(() =>
            this._fixture.AgentOpenAIClient.GetProjectResponsesClient().GetResponseAsync(responseId));
    }

    [Fact]
    public async Task StoredFalse_WithPreviousResponseId_ReadsForkHistoryAndDoesNotAppendAsync()
    {
        // Contract: a store=true head establishes a retrievable fork that carries history. store=false
        // continuations chained to it via previous_response_id read that history transparently but
        // never persist their own response, so any number of store=false turns can reuse the same fork
        // without appending to it.
        var agent = this._fixture.Agent;
        var perAgent = this._fixture.AgentOpenAIClient.GetProjectResponsesClient();

        // Head turn: store=true (default). Establishes the fork with a fact and is retrievable.
        var head = await agent.RunAsync("Remember the number 73. Acknowledge briefly.");
        var headId = head.ResponseId;
        Assert.False(string.IsNullOrWhiteSpace(headId));
        var fetchedHead = await perAgent.GetResponseAsync(headId!);
        Assert.NotNull(fetchedHead.Value);

        ChatClientAgentRunOptions ContinuationOnFork() => new(new ChatOptions
        {
            RawRepresentationFactory = _ => new CreateResponseOptions
            {
                StoredOutputEnabled = false,
                PreviousResponseId = headId,
            },
        });

        // First store=false continuation: reads the fork history (recalls 73) but is not persisted.
        var c1 = await agent.RunAsync("What number did I just tell you?", options: ContinuationOnFork());
        Assert.Contains("73", c1.Text);
        Assert.NotEqual(headId, c1.ResponseId);
        await Assert.ThrowsAnyAsync<Exception>(() => perAgent.GetResponseAsync(c1.ResponseId!));

        // Second store=false continuation on the SAME fork: still recalls, still does not append.
        var c2 = await agent.RunAsync("State that number one more time.", options: ContinuationOnFork());
        Assert.Contains("73", c2.Text);
        await Assert.ThrowsAnyAsync<Exception>(() => perAgent.GetResponseAsync(c2.ResponseId!));

        // The fork head is unchanged and still retrievable after the store=false continuations.
        var fetchedHeadAgain = await perAgent.GetResponseAsync(headId!);
        Assert.NotNull(fetchedHeadAgain.Value);
    }

    [Fact]
    public async Task StoredFalse_WithConversationId_ReadsHistoryButDoesNotAppendAsync()
    {
        // Conversation-id analog of the previous_response_id fork contract: a store=true head populates
        // the conversation with history; store=false continuations bound to the same conversation read
        // that history transparently but never append to it, so the conversation can be reused by any
        // number of store=false turns without growing.
        var agent = this._fixture.Agent;
        var conversationId = await this._fixture.CreateConversationAsync();
        try
        {
            var stored = new ChatClientAgentRunOptions(new ChatOptions { ConversationId = conversationId });
            ChatClientAgentRunOptions ContinuationOnConversation() => new(new ChatOptions
            {
                ConversationId = conversationId,
                RawRepresentationFactory = _ => new CreateResponseOptions { StoredOutputEnabled = false },
            });

            // Head turn: store=true, populates the conversation with a fact.
            await agent.RunAsync("Remember the number 99. Acknowledge briefly.", options: stored);
            var afterHeadCount = await this._fixture.CountConversationItemsAsync(conversationId);
            Assert.True(afterHeadCount > 0);

            // First store=false continuation: reads the conversation history (recalls 99) but does not append.
            var c1 = await agent.RunAsync("What number did I just tell you?", options: ContinuationOnConversation());
            Assert.Contains("99", c1.Text);
            Assert.Equal(afterHeadCount, await this._fixture.CountConversationItemsAsync(conversationId));

            // Second store=false continuation on the SAME conversation: still recalls, still does not append.
            var c2 = await agent.RunAsync("State that number one more time.", options: ContinuationOnConversation());
            Assert.Contains("99", c2.Text);
            Assert.Equal(afterHeadCount, await this._fixture.CountConversationItemsAsync(conversationId));
        }
        finally
        {
            await this._fixture.DeleteConversationAsync(conversationId);
        }
    }

    [Fact]
    public async Task MultiTurn_WithPreviousResponseId_PreservesContextAsync()
    {
        // Arrange
        var agent = this._fixture.Agent;
        var session = await agent.CreateSessionAsync();

        // Act
        var first = await agent.RunAsync("My favorite number is 42. Acknowledge briefly.", session);
        Assert.False(string.IsNullOrWhiteSpace(first.Text));

        var second = await agent.RunAsync("What number did I just tell you?", session);

        // Assert
        Assert.Contains("42", second.Text);
    }

    [Fact]
    public async Task MultiTurn_WithPreviousResponseId_RecoversAcrossThreeTurnsAsync()
    {
        // Arrange: recover the conversation across three turns purely via the previous_response_id
        // chain (store=true). Each turn must land on the same hosted MAF session so earlier facts hold.
        var agent = this._fixture.Agent;
        var session = await agent.CreateSessionAsync();

        // Act
        var t1 = await agent.RunAsync("Remember two facts: my dog is named Rex and I live in Lisbon. Acknowledge briefly.", session);
        Assert.False(string.IsNullOrWhiteSpace(t1.Text));
        var t2 = await agent.RunAsync("What is my dog's name?", session);
        var t3 = await agent.RunAsync("Which city do I live in?", session);

        // Assert: both facts survive across the chain.
        Assert.Contains("Rex", t2.Text, StringComparison.OrdinalIgnoreCase);
        Assert.Contains("Lisbon", t3.Text, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public async Task MultiTurn_WithConversationId_PreservesContextAsync()
    {
        // Arrange
        var agent = this._fixture.Agent;
        var conversationId = await this._fixture.CreateConversationAsync();
        try
        {
            var options = new ChatClientAgentRunOptions(new ChatOptions { ConversationId = conversationId });

            // Act
            var first = await agent.RunAsync("My favorite color is teal. Acknowledge briefly.", options: options);
            Assert.False(string.IsNullOrWhiteSpace(first.Text));

            var second = await agent.RunAsync("What color did I just tell you?", options: options);

            // Assert
            Assert.Contains("teal", second.Text, StringComparison.OrdinalIgnoreCase);
        }
        finally
        {
            await this._fixture.DeleteConversationAsync(conversationId);
        }
    }
}
