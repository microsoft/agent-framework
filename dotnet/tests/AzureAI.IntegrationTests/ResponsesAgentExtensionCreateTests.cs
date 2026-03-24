// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Threading.Tasks;
using AgentConformance.IntegrationTests.Support;
using Azure.AI.Projects;
using Microsoft.Agents.AI;
using Microsoft.Agents.AI.AzureAI;
using Microsoft.Extensions.AI;
using Shared.IntegrationTests;

namespace AzureAI.IntegrationTests;

/// <summary>
/// Integration tests for non-versioned <see cref="ChatClientAgent"/> creation via <see cref="AIProjectClient"/> extension methods.
/// </summary>
public class ResponsesAgentExtensionCreateTests
{
    private static Uri Endpoint => new(TestConfiguration.GetRequiredValue(TestSettings.AzureAIProjectEndpoint));

    private static string Model => TestConfiguration.GetRequiredValue(TestSettings.AzureAIModelDeploymentName);

    private readonly AIProjectClient _client = new(Endpoint, TestAzureCliCredentials.CreateAzureCliCredential());

    [Fact]
    public async Task AsAIAgent_WithModelAndInstructions_CreatesChatClientAgentAndRunsAsync()
    {
        // Arrange
        const string AgentName = "ResponsesAgentExtensionSimple";
        const string AgentDescription = "Integration test agent created from AIProjectClient.AsAIAgent(model, instructions).";
        const string VerificationToken = "integration-extension-ok";

        FoundryAgent agent = this._client.AsAIAgent(
            model: Model,
            instructions: $"You are a helpful assistant. When asked for verification, reply with exactly '{VerificationToken}'.",
            name: AgentName,
            description: AgentDescription);

        AgentSession session = await agent.CreateSessionAsync();

        try
        {
            // Act
            AgentResponse response = await agent.RunAsync("Return the verification token.", session);

            // Assert
            Assert.NotNull(agent);
            Assert.Equal(AgentName, agent.Name);
            Assert.Equal(AgentDescription, agent.Description);
            Assert.Same(this._client, agent.GetService<AIProjectClient>());
            Assert.NotNull(agent.GetService<IChatClient>());
            Assert.Contains(VerificationToken, response.Text, StringComparison.OrdinalIgnoreCase);
        }
        finally
        {
            await DeleteSessionAsync(this._client, session);
        }
    }

    [Fact]
    public async Task AsAIAgent_WithOptions_CreatesChatClientAgentAndRunsAsync()
    {
        // Arrange
        const string VerificationToken = "integration-options-ok";
        ChatClientAgentOptions options = new()
        {
            Name = "ResponsesAgentExtensionOptions",
            Description = "Integration test agent created from AIProjectClient.AsAIAgent(options).",
            ChatOptions = new ChatOptions
            {
                ModelId = Model,
                Instructions = $"You are a helpful assistant. When asked for verification, reply with exactly '{VerificationToken}'.",
            },
        };

        FoundryAgent agent = this._client.AsAIAgent(options);
        ChatClientAgentSession session = await agent.CreateConversationSessionAsync();

        try
        {
            // Act
            AgentResponse response = await agent.RunAsync("Return the verification token.", session);

            // Assert
            Assert.StartsWith("conv_", session.ConversationId, StringComparison.OrdinalIgnoreCase);
            Assert.Equal(options.Name, agent.Name);
            Assert.Equal(options.Description, agent.Description);
            Assert.Same(this._client, agent.GetService<AIProjectClient>());
            Assert.Contains(VerificationToken, response.Text, StringComparison.OrdinalIgnoreCase);
        }
        finally
        {
            await DeleteSessionAsync(this._client, session);
        }
    }

    private static async Task DeleteSessionAsync(AIProjectClient client, AgentSession session)
    {
        ChatClientAgentSession typedSession = (ChatClientAgentSession)session;

        if (typedSession.ConversationId?.StartsWith("conv_", StringComparison.OrdinalIgnoreCase) == true)
        {
            await client.GetProjectOpenAIClient().GetProjectConversationsClient().DeleteConversationAsync(typedSession.ConversationId);
        }
        else if (typedSession.ConversationId?.StartsWith("resp_", StringComparison.OrdinalIgnoreCase) == true)
        {
            await DeleteResponseChainAsync(client, typedSession.ConversationId);
        }
    }

    private static async Task DeleteResponseChainAsync(AIProjectClient client, string lastResponseId)
    {
        var responsesClient = client.GetProjectOpenAIClient().GetProjectResponsesClient();
        var response = await responsesClient.GetResponseAsync(lastResponseId);
        await responsesClient.DeleteResponseAsync(lastResponseId);

        if (response.Value.PreviousResponseId is not null)
        {
            await DeleteResponseChainAsync(client, response.Value.PreviousResponseId);
        }
    }
}
