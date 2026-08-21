// Copyright (c) Microsoft. All rights reserved.

#pragma warning disable AAIP001 // Agent session admin APIs are experimental
#pragma warning disable MEAI001 // FoundryChatOptionsExtensions / OpenAIRequestPolicies are experimental

using System;
using System.ClientModel.Primitives;
using System.Collections.Generic;
using System.Text.RegularExpressions;
using System.Threading;
using System.Threading.Tasks;
using AgentConformance.IntegrationTests.Support;
using Azure.AI.Extensions.OpenAI;
using Azure.AI.Projects.Agents;
using Foundry.Hosting.IntegrationTests.Fixtures;
using Microsoft.Agents.AI;
using Microsoft.Agents.AI.Foundry;
using Microsoft.Extensions.AI;
using Shared.IntegrationTests;

namespace Foundry.Hosting.IntegrationTests;

/// <summary>
/// Live tests for client-side Foundry hosted session sticky behavior and per-call
/// <c>x-ms-user-identity</c> pass-through against a real hosted agent.
/// </summary>
/// <remarks>
/// <para>
/// These tests build a <see cref="FoundryAgent"/> against the fixture's agent endpoint so the
/// production request pipeline (<c>FoundryHostedRequestAgent</c>, session sticky, user-identity
/// header) is exercised. The fixture's default <see cref="HostedAgentFixture.Agent"/> is a plain
/// chat-client agent and is intentionally not used here.
/// </para>
/// <para>
/// Requires the caller credential to be allowed to send <c>x-ms-user-identity</c> (delegation).
/// Without that permission the user-identity tests fail at the platform with 403 rather than an
/// assertion mismatch.
/// </para>
/// </remarks>
[Trait("Category", "FoundryHostedAgents")]
public sealed class HostedSessionAndUserIdentityTests(UserIdentityHostedAgentFixture fixture)
    : IClassFixture<UserIdentityHostedAgentFixture>
{
    private const string FoundryFeaturesHeader = "Foundry-Features";
    private const string HostedAgentsFeatureValue = "HostedAgents=V1Preview,AgentEndpoints=V1Preview";
    private static readonly Regex s_userIdToken = new(@"USER-ID:(\S+)", RegexOptions.CultureInvariant | RegexOptions.Compiled);

    private readonly UserIdentityHostedAgentFixture _fixture = fixture;

    [Fact(Skip = "Requires live Foundry hosted agent image, bootstrap it-user-identity, and delegation permission for x-ms-user-identity.")]
    public async Task ServiceManagedSession_BecomesStickyAndIsReusedAsync()
    {
        // Arrange
        FoundryAgent agent = this.CreateFoundryAgent();
        ChatClientAgentSession session = await agent.CreateFoundryHostedAgentSessionAsync();
        Assert.Null(session.FoundryHostedAgentSessionId);

        string? hostedSessionId = null;
        try
        {
            // Act: first run lets Foundry create the sandbox; sticky id is written from the response.
            var first = await agent.RunAsync("Reply with the single word ready.", session);
            Assert.False(string.IsNullOrWhiteSpace(first.Text));

            hostedSessionId = session.FoundryHostedAgentSessionId;
            Assert.False(string.IsNullOrWhiteSpace(hostedSessionId));

            // Act: second run reuses the same AgentSession and must keep the same sticky id.
            var second = await agent.RunAsync("Reply with the single word again.", session);
            Assert.False(string.IsNullOrWhiteSpace(second.Text));

            // Assert
            Assert.Equal(hostedSessionId, session.FoundryHostedAgentSessionId);
        }
        finally
        {
            await this.TryDeleteSessionAsync(hostedSessionId);
        }
    }

    [Fact(Skip = "Requires live Foundry hosted agent image, bootstrap it-user-identity, and AgentAdministration CreateSession.")]
    public async Task UserManagedSession_PinIsStickyAndMatchesAdminSessionAsync()
    {
        // Arrange: provision sandbox via admin API (Python using_deployed_agent path).
        AgentAdministrationClient admin = this.CreateAdminClient();
        ProjectAgentSession platformSession = await admin.CreateSessionAsync(
            this._fixture.AgentName,
            new VersionRefIndicator(this._fixture.AgentVersion));

        string hostedSessionId = platformSession.AgentSessionId;
        await WaitForSessionActiveAsync(admin, this._fixture.AgentName, hostedSessionId);

        FoundryAgent agent = this.CreateFoundryAgent();
        ChatClientAgentSession session = await agent.CreateFoundryHostedAgentSessionAsync(hostedSessionId: hostedSessionId);
        Assert.Equal(hostedSessionId, session.FoundryHostedAgentSessionId);

        try
        {
            // Act
            var response = await agent.RunAsync("Reply with the single word pinned.", session);

            // Assert
            Assert.False(string.IsNullOrWhiteSpace(response.Text));
            Assert.Equal(hostedSessionId, session.FoundryHostedAgentSessionId);
        }
        finally
        {
            await this.TryDeleteSessionAsync(hostedSessionId);
        }
    }

    [Fact(Skip = "Requires live Foundry hosted agent image, bootstrap it-user-identity, and delegation permission for x-ms-user-identity.")]
    public async Task SameHostedSandbox_DifferentAgentSessionsAndUserIdentities_YieldsDistinctUsersAsync()
    {
        // Arrange: two different AgentSession instances share one Foundry hosted sandbox id.
        // ConversationId is per AgentSession (chat trail). HostedAgentSessionId is the sandbox.
        // Reusing one AgentSession across identities reuses previous_response_id and 404s under
        // per-user response partitioning; separate AgentSessions avoid that while keeping the sandbox.
        FoundryAgent agent = this.CreateFoundryAgent();
        string? hostedSessionId = null;

        try
        {
            // Act: alice creates the sandbox via service-managed sticky capture.
            ChatClientAgentSession aliceSession = await agent.CreateFoundryHostedAgentSessionAsync();
            string aliceUserId = await this.RunAndReadUserIdAsync(agent, aliceSession, "alice-it");
            hostedSessionId = aliceSession.FoundryHostedAgentSessionId;
            Assert.False(string.IsNullOrWhiteSpace(hostedSessionId));
            string? aliceConversationId = aliceSession.ConversationId;

            // Act: bob gets a fresh AgentSession pinned to the same hosted sandbox.
            ChatClientAgentSession bobSession = await agent.CreateFoundryHostedAgentSessionAsync(hostedSessionId: hostedSessionId);
            Assert.NotSame(aliceSession, bobSession);
            Assert.Equal(hostedSessionId, bobSession.FoundryHostedAgentSessionId);

            string bobUserId = await this.RunAndReadUserIdAsync(agent, bobSession, "bob-it");

            // Assert: hosted sandbox stays the same on both sessions after bob's response.
            Assert.Equal(hostedSessionId, aliceSession.FoundryHostedAgentSessionId);
            Assert.Equal(hostedSessionId, bobSession.FoundryHostedAgentSessionId);

            // Assert: conversation trails stay independent (must not share ConversationId).
            string? bobConversationId = bobSession.ConversationId;
            Assert.False(
                aliceConversationId is not null
                && bobConversationId is not null
                && string.Equals(aliceConversationId, bobConversationId, StringComparison.Ordinal),
                $"ConversationId must differ across AgentSessions. alice='{aliceConversationId}', bob='{bobConversationId}'.");
            if (aliceConversationId is not null || bobConversationId is not null)
            {
                Assert.NotEqual(aliceConversationId, bobConversationId);
            }

            // Assert: platform user keys differ for alice vs bob.
            Assert.NotEqual("missing", aliceUserId);
            Assert.NotEqual("missing", bobUserId);
            Assert.NotEqual(aliceUserId, bobUserId);
        }
        finally
        {
            await this.TryDeleteSessionAsync(hostedSessionId);
        }
    }

    [Fact(Skip = "Requires live Foundry hosted agent image, bootstrap it-user-identity, and delegation permission for x-ms-user-identity.")]
    public async Task SameSession_SameUserIdentity_YieldsStablePlatformUserIdAsync()
    {
        // Arrange
        FoundryAgent agent = this.CreateFoundryAgent();
        ChatClientAgentSession session = await agent.CreateFoundryHostedAgentSessionAsync();
        string? hostedSessionId = null;

        try
        {
            // Act
            string first = await this.RunAndReadUserIdAsync(agent, session, "stable-user-it");
            hostedSessionId = session.FoundryHostedAgentSessionId;
            string second = await this.RunAndReadUserIdAsync(agent, session, "stable-user-it");

            // Assert
            Assert.False(string.IsNullOrWhiteSpace(hostedSessionId));
            Assert.Equal(hostedSessionId, session.FoundryHostedAgentSessionId);
            Assert.NotEqual("missing", first);
            Assert.Equal(first, second);
        }
        finally
        {
            await this.TryDeleteSessionAsync(hostedSessionId);
        }
    }

    private async Task<string> RunAndReadUserIdAsync(FoundryAgent agent, AgentSession session, string userIdentity)
    {
        var options = new ChatClientAgentRunOptions(
            new ChatOptions().WithFoundryHostedAgentUserIdentity(userIdentity));

        var response = await agent.RunAsync(
            "Acknowledge the request briefly.",
            session,
            options);

        Assert.False(string.IsNullOrWhiteSpace(response.Text));
        Match match = s_userIdToken.Match(response.Text);
        Assert.True(match.Success, $"Expected USER-ID:<value> token in response text. Actual: {response.Text}");
        return match.Groups[1].Value;
    }

    /// <summary>
    /// Builds a <see cref="FoundryAgent"/> against this fixture's hosted agent endpoint with the
    /// preview feature headers required for hosted agent traffic.
    /// </summary>
    private FoundryAgent CreateFoundryAgent()
    {
        var endpoint = new Uri(TestConfiguration.GetRequiredValue(TestSettings.AzureAIProjectEndpoint));
        var credential = TestAzureCliCredentials.CreateAzureCliCredential();
        Uri agentEndpoint = new($"{endpoint.ToString().TrimEnd('/')}/agents/{this._fixture.AgentName}/endpoint/protocols/openai");

        var options = new ProjectOpenAIClientOptions
        {
            AgentName = this._fixture.AgentName,
        };
        options.AddPolicy(new FoundryFeaturesPolicy(HostedAgentsFeatureValue), PipelinePosition.PerCall);

        return new FoundryAgent(agentEndpoint, credential, options);
    }

    private AgentAdministrationClient CreateAdminClient()
    {
        var endpoint = new Uri(TestConfiguration.GetRequiredValue(TestSettings.AzureAIProjectEndpoint));
        var credential = TestAzureCliCredentials.CreateAzureCliCredential();
        var adminOptions = new AgentAdministrationClientOptions();
        adminOptions.AddPolicy(new FoundryFeaturesPolicy(HostedAgentsFeatureValue), PipelinePosition.PerCall);
        return new AgentAdministrationClient(endpoint, credential, adminOptions);
    }

    private async Task TryDeleteSessionAsync(string? hostedSessionId)
    {
        if (string.IsNullOrWhiteSpace(hostedSessionId))
        {
            return;
        }

        try
        {
            AgentAdministrationClient admin = this.CreateAdminClient();
            await admin.DeleteSessionAsync(this._fixture.AgentName, hostedSessionId);
        }
        catch
        {
            // Best-effort cleanup; platform TTL reclaims orphaned sessions.
        }
    }

    private static async Task WaitForSessionActiveAsync(
        AgentAdministrationClient admin,
        string agentName,
        string sessionId,
        TimeSpan? timeout = null)
    {
        TimeSpan limit = timeout ?? TimeSpan.FromMinutes(3);
        DateTimeOffset deadline = DateTimeOffset.UtcNow + limit;
        ProjectAgentSession session = await admin.GetSessionAsync(agentName, sessionId);

        while (session.Status != AgentSessionStatus.Active
            && session.Status != AgentSessionStatus.Failed
            && session.Status != AgentSessionStatus.Deleted
            && session.Status != AgentSessionStatus.Expired)
        {
            if (DateTimeOffset.UtcNow > deadline)
            {
                throw new TimeoutException(
                    $"Hosted session '{sessionId}' for agent '{agentName}' did not become Active within {limit.TotalSeconds:F0}s. Last status: {session.Status}.");
            }

            await Task.Delay(TimeSpan.FromMilliseconds(500), CancellationToken.None);
            session = await admin.GetSessionAsync(agentName, sessionId);
        }

        Assert.Equal(AgentSessionStatus.Active, session.Status);
    }

    /// <summary>Pipeline policy that stamps the Foundry preview feature header.</summary>
    private sealed class FoundryFeaturesPolicy(string features) : PipelinePolicy
    {
        public override void Process(PipelineMessage message, IReadOnlyList<PipelinePolicy> pipeline, int currentIndex)
        {
            message.Request.Headers.Set(FoundryFeaturesHeader, features);
            ProcessNext(message, pipeline, currentIndex);
        }

        public override ValueTask ProcessAsync(PipelineMessage message, IReadOnlyList<PipelinePolicy> pipeline, int currentIndex)
        {
            message.Request.Headers.Set(FoundryFeaturesHeader, features);
            return ProcessNextAsync(message, pipeline, currentIndex);
        }
    }
}
