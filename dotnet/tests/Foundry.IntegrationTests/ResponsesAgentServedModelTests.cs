// Copyright (c) Microsoft. All rights reserved.

using System;
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
        Assert.NotNull(response.ModelId);
        Assert.False(string.IsNullOrWhiteSpace(response.ModelId));

        // The served model is a dated snapshot (e.g. "gpt-5-nano-2025-08-07") that differs
        // from the deployment alias. We assert it is not equal to the alias to confirm the
        // x-ms-served-model header was picked up by the policy and propagated to ModelId.
        Assert.NotEqual(DeploymentName, response.ModelId);
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
        Assert.False(string.IsNullOrWhiteSpace(chatResponse!.ModelId));
        Assert.NotEqual(DeploymentName, chatResponse.ModelId);
    }
}
