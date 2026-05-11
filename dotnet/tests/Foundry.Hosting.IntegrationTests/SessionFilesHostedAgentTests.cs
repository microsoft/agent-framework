// Copyright (c) Microsoft. All rights reserved.

#pragma warning disable AAIP001 // AgentSessionFiles is experimental
#pragma warning disable OPENAI001 // CreateResponseOptions is experimental

using System;
using System.ClientModel;
using System.ClientModel.Primitives;
using System.Collections.Generic;
using System.IO;
using System.Threading;
using System.Threading.Tasks;
using AgentConformance.IntegrationTests.Support;
using Azure.AI.Extensions.OpenAI;
using Azure.AI.Projects;
using Azure.AI.Projects.Agents;
using Foundry.Hosting.IntegrationTests.Fixtures;
using Microsoft.Agents.AI;
using Microsoft.Extensions.AI;
using OpenAI.Responses;
using Shared.IntegrationTests;

namespace Foundry.Hosting.IntegrationTests;

/// <summary>
/// End-to-end integration test for the Hosted-Files style scenario: a file uploaded by the client
/// via the alpha <see cref="AgentSessionFiles"/> SDK is read by the deployed hosted agent's
/// container-side <c>ReadFile</c> tool and surfaces in <see cref="AIAgent.RunAsync(string, AgentSession, AgentRunOptions, CancellationToken)"/>.
/// </summary>
/// <remarks>
/// <para>
/// Routing both invocations to the same per-session container requires two clients on the same
/// agent-scoped <see cref="ProjectOpenAIClient"/>: a <see cref="ProjectConversationsClient"/> to
/// pre-create a conversation bound to the agent endpoint, and a <see cref="ProjectResponsesClient"/>
/// for invocation. The session id resolved by the platform on the first call is captured from the
/// <c>x-agent-session-id</c> response header and used to target the
/// <see cref="AgentSessionFiles"/> upload at the same session's <c>$HOME</c>. The second call
/// carries the same conversation_id so it lands in the same container and the agent's
/// <c>ReadFile</c> tool sees the upload.
/// </para>
/// </remarks>
[Trait("Category", "FoundryHostedAgents")]
public sealed class SessionFilesHostedAgentTests(SessionFilesHostedAgentFixture fixture) : IClassFixture<SessionFilesHostedAgentFixture>
{
    private const string FoundryFeaturesHeader = "Foundry-Features";
    private const string HostedAgentsFeatureValue = "HostedAgents=V1Preview,AgentEndpoints=V1Preview";
    private const string SessionIdHeader = "x-agent-session-id";

    private const string TestDataFileName = "contoso_q1_2026_report.txt";

    /// <summary>Token that appears verbatim in the test data file. Proof the agent read what we uploaded.</summary>
    private const string ExpectedTokenInFile = "1,482.6";

    private readonly SessionFilesHostedAgentFixture _fixture = fixture;

    [Fact]
    public async Task UploadedFile_IsReadByHostedAgentAsync()
    {
        // Arrange
        string localPath = Path.Combine(AppContext.BaseDirectory, "TestData", TestDataFileName);
        Assert.True(
            File.Exists(localPath),
            $"Test data file not found at '{localPath}'. Confirm the linked Content entry in the csproj.");

        var endpoint = new Uri(TestConfiguration.GetRequiredValue(TestSettings.AzureAIProjectEndpoint));
        var credential = TestAzureCliCredentials.CreateAzureCliCredential();

        // Admin client + AgentSessionFiles for upload/list/delete (alpha SDK).
        var adminOptions = new AgentAdministrationClientOptions();
        adminOptions.AddPolicy(new FoundryFeaturesPolicy(HostedAgentsFeatureValue), PipelinePosition.PerCall);
        var adminClient = new AgentAdministrationClient(endpoint, credential, adminOptions);
        var sessionFiles = adminClient.GetAgentSessionFiles();

        // Build the per-agent OpenAI client. The conversation is created on this client so it is
        // bound to the agent endpoint URL (`/agents/{name}/endpoint/protocols/openai/conversations`).
        // A header-capture policy reads the `x-agent-session-id` the platform stamps on every reply.
        var headerCapture = new ResponseHeaderCapturePolicy(SessionIdHeader);
        var openAIOptions = new ProjectOpenAIClientOptions { AgentName = this._fixture.AgentName };
        openAIOptions.AddPolicy(new FoundryFeaturesPolicy(HostedAgentsFeatureValue), PipelinePosition.PerCall);
        openAIOptions.AddPolicy(headerCapture, PipelinePosition.PerCall);
        var openAIClient = new ProjectOpenAIClient(endpoint, credential, openAIOptions);
        var conversations = openAIClient.GetProjectConversationsClient();
        var responses = openAIClient.GetProjectResponsesClient();

        // Step 1 — create a conversation bound to the agent endpoint. Subsequent /responses calls
        // tagged with this conversation_id route to the same per-session container.
        var conversation = await conversations.CreateProjectConversationAsync();
        string conversationId = conversation.Value.Id;

        try
        {
            // Step 2 — warm-up call. Provisions the per-session container under the conversation and
            // lets us read back the resolved agent_session_id from the response header.
            var agent = responses.AsIChatClient().AsAIAgent(name: this._fixture.AgentName);
            var convOptions = new ChatClientAgentRunOptions(new ChatOptions { ConversationId = conversationId });

            var warmup = await agent.RunAsync(
                "Reply with the single word 'ready' and nothing else.",
                options: convOptions);
            Assert.False(string.IsNullOrWhiteSpace(warmup.Text));

            string agentSessionId = headerCapture.LastValue
                ?? throw new InvalidOperationException(
                    $"Expected '{SessionIdHeader}' response header on warm-up but got none.");

            try
            {
                // Step 3 — upload the file via the alpha AgentSessionFiles SDK to that exact session's $HOME.
                SessionFileWriteResponse writeResponse = await sessionFiles.UploadSessionFileAsync(
                    agentName: this._fixture.AgentName,
                    sessionId: agentSessionId,
                    sessionStoragePath: TestDataFileName,
                    localPath: localPath);

                long expectedBytes = new FileInfo(localPath).Length;
                Assert.Equal(expectedBytes, writeResponse.BytesWritten);

                SessionDirectoryListResponse listing = await sessionFiles.GetSessionFilesAsync(
                    agentName: this._fixture.AgentName,
                    sessionId: agentSessionId,
                    sessionStoragePath: ".");
                Assert.Contains(
                    listing.Entries,
                    e => e.Name == TestDataFileName && !e.IsDirectory && e.Size == expectedBytes);

                // Step 4 — invoke the agent again on the SAME conversation. The platform routes back to
                // the same agent_session_id container, so the agent's ReadFile tool sees the upload.
                // The platform mutates session/conversation revision when AgentSessionFiles uploads land,
                // so an immediate /responses follow-up races and 400's with "modified concurrently. Please
                // retry." — the response message literally tells us to retry. Bounded retry handles it.
                var readOptions = new CreateResponseOptions { AgentConversationId = conversationId };
                readOptions.InputItems.Add(ResponseItem.CreateUserMessageItem(
                    $"Read {TestDataFileName} from $HOME and quote the headline total revenue figure verbatim, no commentary."));

                ClientResult<ResponseResult> rawResponse = null!;
                const int MaxAttempts = 5;
                for (int attempt = 1; attempt <= MaxAttempts; attempt++)
                {
                    try
                    {
                        rawResponse = await responses.CreateResponseAsync(readOptions);
                        break;
                    }
                    catch (ClientResultException ex) when (
                        ex.Status == 400 &&
                        ex.Message.Contains("modified concurrently", StringComparison.OrdinalIgnoreCase) &&
                        attempt < MaxAttempts)
                    {
                        await Task.Delay(TimeSpan.FromSeconds(2 * attempt));
                    }
                }

                string responseText = rawResponse.Value.GetOutputText() ?? string.Empty;

                Assert.Equal(agentSessionId, headerCapture.LastValue);

                // Assert: the response contains the deterministic token from the file.
                Assert.False(string.IsNullOrWhiteSpace(responseText));
                Assert.Contains(ExpectedTokenInFile, responseText);
            }
            finally
            {
                // Best-effort cleanup of the uploaded file. The session itself is left for TTL expiry —
                // the platform owns its lifecycle (no isolation key in our hands).
                try
                {
                    await sessionFiles.DeleteSessionFileAsync(
                        agentName: this._fixture.AgentName,
                        sessionId: agentSessionId,
                        path: TestDataFileName);
                }
                catch
                {
                    // Ignore.
                }
            }
        }
        finally
        {
            await this._fixture.DeleteConversationAsync(conversationId);
        }
    }

    /// <summary>
    /// Captures a response header value on every pipeline call. Latest value is read after the
    /// response completes. Used to grab the platform's <c>x-agent-session-id</c> stamp.
    /// </summary>
    private sealed class ResponseHeaderCapturePolicy(string headerName) : PipelinePolicy
    {
        private readonly string _headerName = headerName;
        private string? _lastValue;

        public string? LastValue => Volatile.Read(ref this._lastValue);

        public override void Process(PipelineMessage message, IReadOnlyList<PipelinePolicy> pipeline, int currentIndex)
        {
            ProcessNext(message, pipeline, currentIndex);
            this.Capture(message);
        }

        public override async ValueTask ProcessAsync(PipelineMessage message, IReadOnlyList<PipelinePolicy> pipeline, int currentIndex)
        {
            await ProcessNextAsync(message, pipeline, currentIndex).ConfigureAwait(false);
            this.Capture(message);
        }

        private void Capture(PipelineMessage message)
        {
            if (message.Response is not null &&
                message.Response.Headers.TryGetValue(this._headerName, out var value) &&
                !string.IsNullOrEmpty(value))
            {
                Volatile.Write(ref this._lastValue, value);
            }
        }
    }

    private sealed class FoundryFeaturesPolicy(string features) : PipelinePolicy
    {
        public override void Process(PipelineMessage message, IReadOnlyList<PipelinePolicy> pipeline, int currentIndex)
        {
            this.SetHeader(message);
            ProcessNext(message, pipeline, currentIndex);
        }

        public override async ValueTask ProcessAsync(PipelineMessage message, IReadOnlyList<PipelinePolicy> pipeline, int currentIndex)
        {
            this.SetHeader(message);
            await ProcessNextAsync(message, pipeline, currentIndex).ConfigureAwait(false);
        }

        private void SetHeader(PipelineMessage message)
        {
            message.Request.Headers.Remove(FoundryFeaturesHeader);
            message.Request.Headers.Add(FoundryFeaturesHeader, features);
        }
    }
}
