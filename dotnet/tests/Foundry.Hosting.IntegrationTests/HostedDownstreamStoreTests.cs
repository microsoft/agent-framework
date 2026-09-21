// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Threading.Tasks;
using Foundry.Hosting.IntegrationTests.Fixtures;
using Microsoft.Agents.AI;

namespace Foundry.Hosting.IntegrationTests;

/// <summary>
/// Proves a hosted turn is kept once.
/// </summary>
/// <remarks>
/// <para>
/// The AgentServer SDK's storage provider records every hosted turn around the container's handler,
/// and that record is the conversation the caller reads. The agent's own run inside the container
/// talks to its own service, and when that service is asked to keep the turn it writes a second copy
/// of the same exchange, on a trail of its own that nobody reads and nobody reconciles. The caller's
/// conversation looks clean, so the second copy goes unnoticed.
/// </para>
/// <para>
/// The container agent here is an ordinary Foundry <c>ChatClientAgent</c>, like the first hosted agent
/// sample. It is wrapped so that after the run it appends <c>DOWNSTREAM_ID=&lt;id&gt;</c> to the reply,
/// carrying whatever its own run left behind on the service. The tests then go looking for that id:
/// finding it means a second copy exists.
/// </para>
/// </remarks>
[Trait("Category", "FoundryHostedAgents")]
public sealed class HostedDownstreamStoreTests(DownstreamStoreHostedAgentFixture fixture) : IClassFixture<DownstreamStoreHostedAgentFixture>
{
    private const string IdPrefix = "DOWNSTREAM_ID=";
    private const string NoId = "none";

    private readonly DownstreamStoreHostedAgentFixture _fixture = fixture;

    [Fact]
    public async Task StoredTurn_LeavesNothingBehindOnTheAgentsOwnServiceAsync()
    {
        // Arrange: a session bound to a conversation, which is how a caller keeps a hosted agent on one
        // thread. The session carries the conversation, so no per-run options are needed.
        var agent = this._fixture.Agent;
        var chatClientAgent = agent.GetService<ChatClientAgent>();
        Assert.NotNull(chatClientAgent);

        var conversationId = await this._fixture.CreateConversationAsync();
        try
        {
            var session = await chatClientAgent.CreateSessionAsync(conversationId);

            // Act: one stored turn, the way any caller would send it.
            var response = await agent.RunAsync("Reply with the word 'ack'.", session);

            // Assert: the caller's conversation holds the turn, so it was recorded once already.
            var recorded = await this._fixture.ReadConversationMessagesAsync(conversationId);
            Assert.NotEmpty(recorded);

            // And the agent's own run left nothing behind that can be read back off the service.
            await this.AssertNothingWasLeftBehindAsync(response.Text);
        }
        finally
        {
            await this._fixture.DeleteConversationAsync(conversationId);
        }
    }

    [Fact]
    public async Task MultiTurn_LeavesNothingBehindOnTheAgentsOwnServiceAsync()
    {
        // Arrange: the agent's own default session, with nothing set up ahead of time. Whatever the
        // hosted agent keeps for the caller lands on the session once the first turn comes back.
        var agent = this._fixture.Agent;
        var session = await agent.CreateSessionAsync();

        // Act
        var first = await agent.RunAsync("Remember the number 73. Acknowledge briefly.", session);
        var second = await agent.RunAsync("What number did I just tell you?", session);

        // Assert: the conversation works, so history is reaching the model.
        Assert.Contains("73", second.Text);

        // The hosted agent handed the caller something to continue from, and it is on the session.
        var keptForTheCaller = (session as ChatClientAgentSession)?.ConversationId;
        Assert.False(
            string.IsNullOrWhiteSpace(keptForTheCaller),
            "The hosted agent did not hand the caller anything to continue the conversation from.");

        // Every turn's own run, though, left nothing behind on the service.
        await this.AssertNothingWasLeftBehindAsync(first.Text);
        await this.AssertNothingWasLeftBehindAsync(second.Text);
    }

    /// <summary>
    /// Fails when the id the container reported still resolves on the service, which means the agent's
    /// own run kept a second copy of a turn the platform had already recorded.
    /// </summary>
    private async Task AssertNothingWasLeftBehindAsync(string? replyText)
    {
        var downstreamId = ParseDownstreamId(replyText);
        if (downstreamId is null)
        {
            return;
        }

        var found = await this._fixture.TryReadResponseAsync(downstreamId);
        Assert.True(
            found is null,
            $"The agent's own run left a second copy of the turn on the service, readable as '{downstreamId}'.");
    }

    /// <summary>
    /// Reads the id the container reported, or <see langword="null"/> when the run left nothing behind.
    /// </summary>
    private static string? ParseDownstreamId(string? text)
    {
        Assert.False(string.IsNullOrWhiteSpace(text));

        var marker = text!.IndexOf(IdPrefix, StringComparison.Ordinal);
        Assert.True(marker >= 0, $"Expected the container to report '{IdPrefix}...' but got: {text}");

        var value = text[(marker + IdPrefix.Length)..].Trim();
        return value.Length == 0 || value.Equals(NoId, StringComparison.Ordinal) ? null : value;
    }
}
