// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Text.RegularExpressions;
using System.Threading.Tasks;
using AgentConformance.IntegrationTests.Support;
using Azure.AI.Projects;
using Microsoft.Agents.AI;
using Microsoft.Extensions.AI;
using Shared.IntegrationTests;

namespace Foundry.IntegrationTests;

/// <summary>
/// Integration tests validating that the <c>x-ms-served-model</c> response header
/// returned by the Azure OpenAI Responses API is surfaced on <see cref="ChatResponse.ModelId"/>.
/// </summary>
public class ResponsesAgentServedModelTests
{
    // Matches a dated served-model snapshot, e.g. "gpt-5-nano-2025-08-07".
    private static readonly Regex s_snapshotRegex = new(@"-\d{4}-\d{2}-\d{2}$", RegexOptions.Compiled);

    private static Uri Endpoint => new(TestConfiguration.GetRequiredValue(TestSettings.AzureAIProjectEndpoint));

    private static string DeploymentName => TestConfiguration.GetRequiredValue(TestSettings.AzureAIModelDeploymentName);

    private readonly AIProjectClient _client = new(Endpoint, TestAzureCliCredentials.CreateAzureCliCredential());

    [Fact]
    public async Task GetResponseAsync_ReturnsServedModelSnapshotOnModelIdAsync()
    {
        // Arrange
        ChatClientAgent agent = this._client.AsAIAgent(
            model: DeploymentName,
            instructions: "You are a helpful assistant. Reply with a single short word.",
            name: "ServedModelTest");

        IChatClient chatClient = agent.ChatClient;

        // Act
        ChatResponse response = await chatClient.GetResponseAsync(
            [new ChatMessage(ChatRole.User, "Say hi.")],
            new ChatOptions { ModelId = DeploymentName });

        // Assert
        AssertServedModel(response.ModelId);
    }

    [Fact]
    public async Task RunAsync_AgentResponseRawRepresentationCarriesServedModelAsync()
    {
        // Arrange
        ChatClientAgent agent = this._client.AsAIAgent(
            model: DeploymentName,
            instructions: "You are a helpful assistant. Reply with a single short word.",
            name: "ServedModelTestRun");

        // Act
        AgentResponse agentResponse = await agent.RunAsync("Say hi.");

        // Assert
        ChatResponse? chatResponse = agentResponse.RawRepresentation as ChatResponse;
        Assert.NotNull(chatResponse);
        AssertServedModel(chatResponse!.ModelId);
    }

    private static void AssertServedModel(string? modelId)
    {
        Assert.False(string.IsNullOrWhiteSpace(modelId), "ChatResponse.ModelId must be populated.");

        // Primary invariant: the served-model value must look like a dated snapshot
        // (e.g. "gpt-5-nano-2025-08-07"). This is what the x-ms-served-model header carries.
        // Only when the configured deployment name itself already matches the snapshot pattern
        // do we fall back to permitting equality with the deployment alias.
        bool aliasIsSnapshot = s_snapshotRegex.IsMatch(DeploymentName);

        if (aliasIsSnapshot)
        {
            return;
        }

        Assert.Matches(s_snapshotRegex, modelId!);
        Assert.NotEqual(DeploymentName, modelId);
    }
}
