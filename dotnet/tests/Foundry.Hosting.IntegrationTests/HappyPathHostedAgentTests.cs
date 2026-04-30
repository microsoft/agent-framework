// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Linq;
using System.Threading.Tasks;
using Foundry.Hosting.IntegrationTests.Fixtures;
using Microsoft.Agents.AI;
using Azure.AI.Projects;
using Azure.AI.Extensions.OpenAI;
using Microsoft.Extensions.AI;
using OpenAI.Responses;

#pragma warning disable OPENAI001 // Experimental Responses API surfaces

namespace Foundry.Hosting.IntegrationTests;

/// <summary>
/// Round trip and conversation oriented integration tests against a hosted Responses agent.
/// </summary>
public sealed class HappyPathHostedAgentTests(HappyPathHostedAgentFixture fixture) : IClassFixture<HappyPathHostedAgentFixture>
{
    private readonly HappyPathHostedAgentFixture _fixture = fixture;

    [Fact(Skip = "Pending TestContainer build and end to end smoke (step 5).")]
    public async Task RunAsync_ReturnsNonEmptyTextAsync()
    {
        // Arrange
        var agent = this._fixture.Agent;

        // Act
        var response = await agent.RunAsync("Reply with a short greeting.");

        // Assert
        Assert.False(string.IsNullOrWhiteSpace(response.Text));
    }

    [Fact(Skip = "Pending TestContainer build and end to end smoke (step 5).")]
    public async Task RunStreamingAsync_YieldsAtLeastOneUpdateAsync()
    {
        // Arrange
        var agent = this._fixture.Agent;

        // Act
        var collected = new System.Collections.Generic.List<string>();
        await foreach (var update in agent.RunStreamingAsync("Reply with a short greeting."))
        {
            if (!string.IsNullOrEmpty(update.Text))
            {
                collected.Add(update.Text);
            }
        }

        // Assert
        Assert.NotEmpty(collected);
        Assert.False(string.IsNullOrWhiteSpace(string.Concat(collected)));
    }

    [Fact(Skip = "Pending TestContainer build and end to end smoke (step 5).")]
    public async Task MultiTurn_WithPreviousResponseId_PreservesContextAsync()
    {
        // Arrange
        var agent = this._fixture.Agent;

        // Act
        var first = await agent.RunAsync("My favorite number is 42. Acknowledge briefly.");
        Assert.False(string.IsNullOrWhiteSpace(first.Text));

        var session = await agent.CreateSessionAsync();
        var second = await agent.RunAsync("What number did I just tell you?", session, new ChatClientAgentRunOptions());

        // Assert
        Assert.Contains("42", second.Text);
    }

    [Fact(Skip = "Pending TestContainer build and end to end smoke (step 5).")]
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

    [Fact(Skip = "Pending TestContainer build and end to end smoke (step 5).")]
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

        // Attempting to fetch the response should fail because nothing was stored.
        var responsesClient = this._fixture.ProjectClient.GetProjectOpenAIClient().GetProjectResponsesClient();
        await Assert.ThrowsAnyAsync<Exception>(() => responsesClient.GetResponseAsync(responseId));
    }

    [Fact(Skip = "Pending TestContainer build and end to end smoke (step 5).")]
    public async Task StoredFalse_WithPreviousResponseId_ReadsHistoryButDoesNotAppendAsync()
    {
        // Arrange
        var agent = this._fixture.Agent;

        // Turn 1 is stored so the chain head exists.
        var first = await agent.RunAsync("Remember the number 73. Acknowledge briefly.");
        var firstResponseId = first.ResponseId!;

        // Turn 2 is stored=false but reads from turn 1.
        var session = await agent.CreateSessionAsync();
        var optionsNoStore = new ChatClientAgentRunOptions(new ChatOptions
        {
            RawRepresentationFactory = _ => new CreateResponseOptions { StoredOutputEnabled = false }
        });

        // Act
        var second = await agent.RunAsync("What number did I just tell you?", session, optionsNoStore);

        // Assert: model received history (knows the number) but the new response is not persisted.
        Assert.Contains("73", second.Text);
        var responsesClient = this._fixture.ProjectClient.GetProjectOpenAIClient().GetProjectResponsesClient();
        await Assert.ThrowsAnyAsync<Exception>(() => responsesClient.GetResponseAsync(second.ResponseId!));
    }

    [Fact(Skip = "Pending TestContainer build and end to end smoke (step 5).")]
    public async Task StoredFalse_WithConversationId_ReadsHistoryButDoesNotAppendAsync()
    {
        // Arrange
        var agent = this._fixture.Agent;
        var conversationId = await this._fixture.CreateConversationAsync();
        try
        {
            var stored = new ChatClientAgentRunOptions(new ChatOptions { ConversationId = conversationId });
            var notStored = new ChatClientAgentRunOptions(new ChatOptions
            {
                ConversationId = conversationId,
                RawRepresentationFactory = _ => new CreateResponseOptions { StoredOutputEnabled = false }
            });

            // Turn 1 stored, populates the conversation.
            await agent.RunAsync("Remember the number 99. Acknowledge briefly.", options: stored);
            var beforeCount = await this._fixture.CountConversationItemsAsync(conversationId);

            // Act: turn 2 reads from conversation but is not appended.
            var second = await agent.RunAsync("What number did I just tell you?", options: notStored);

            // Assert
            Assert.Contains("99", second.Text);
            var afterCount = await this._fixture.CountConversationItemsAsync(conversationId);
            Assert.Equal(beforeCount, afterCount);
        }
        finally
        {
            await this._fixture.DeleteConversationAsync(conversationId);
        }
    }

    [Fact(Skip = "Pending TestContainer build and end to end smoke (step 5).")]
    public async Task StoredTrue_Default_PersistsResponseInChainAsync()
    {
        // Arrange
        var agent = this._fixture.Agent;

        // Act
        var response = await agent.RunAsync("Reply with the word 'ack'.");

        // Assert
        Assert.False(string.IsNullOrWhiteSpace(response.Text));
        var responsesClient = this._fixture.ProjectClient.GetProjectOpenAIClient().GetProjectResponsesClient();
        var fetched = await responsesClient.GetResponseAsync(response.ResponseId!);
        Assert.NotNull(fetched.Value);
    }

    [Fact(Skip = "Pending TestContainer build and end to end smoke (step 5).")]
    public async Task Instructions_FromContainerDefinition_AreObeyedAsync()
    {
        // Arrange: the container side instructions for happy-path enforce a single word reply
        // (e.g. "Always reply with exactly the single word ECHO."). See TestContainer/Program.cs.
        var agent = this._fixture.Agent;

        // Act
        var response = await agent.RunAsync("Say something useful.");

        // Assert
        Assert.False(string.IsNullOrWhiteSpace(response.Text));
        Assert.Contains("ECHO", response.Text, StringComparison.OrdinalIgnoreCase);
    }
}
