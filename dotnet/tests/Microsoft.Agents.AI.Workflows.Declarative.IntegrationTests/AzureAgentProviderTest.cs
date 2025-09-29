// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Linq;
using System.Threading.Tasks;
using Azure;
using Azure.AI.Agents.Persistent;
using Azure.Identity;
using Microsoft.Agents.AI.Workflows.Declarative.IntegrationTests.Framework;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.Configuration;
using Shared.IntegrationTests;
using Xunit.Abstractions;

namespace Microsoft.Agents.AI.Workflows.Declarative.IntegrationTests;

public sealed class AzureAgentProviderTest(ITestOutputHelper output) : IntegrationTest(output)
{
    private AzureAIConfiguration? _configuration;

    [Fact]
    public async Task ConversationTestAsync()
    {
        // Arrange
        AzureAgentProvider provider = new(this.Configuration.Endpoint, new AzureCliCredential());
        // Act
        string conversationId = await provider.CreateConversationAsync();
        // Assert
        Assert.NotEmpty(conversationId);

        // Arrange & Act
        for (int index = 0; index < 3; ++index)
        {
            await provider.CreateMessageAsync(conversationId, new ChatMessage(ChatRole.User, $"Message #{index * 2}"));
            await provider.CreateMessageAsync(conversationId, new ChatMessage(ChatRole.Assistant, $"Message #{(index * 2) + 1}"));
        }

        // Act
        ChatMessage[] messages = await provider.GetMessagesAsync(conversationId).ToArrayAsync();
        // Assert
        Assert.Equal(6, messages.Length);
        Assert.NotNull(messages[3].MessageId);

        // Act
        ChatMessage message = await provider.GetMessageAsync(conversationId, messages[3].MessageId!);
        // Assert
        Assert.NotNull(message);
        Assert.Equal(messages[3].Text, message.Text);
    }

    [Fact]
    public async Task GetAgentTestAsync()
    {
        // Arrange
        AzureAgentProvider provider = new(this.Configuration.Endpoint, new AzureCliCredential());
        string agentName = $"TestAgent-{DateTime.UtcNow:yyMMdd-HHmmss-fff}";

        string agent1Id = await this.CreateAgentAsync();
        string agent2Id = await this.CreateAgentAsync(agentName);

        // Act
        AIAgent agent1 = await provider.GetAgentAsync(agent1Id);
        // Assert
        Assert.Equal(agent1Id, agent1.Id);

        // Act
        AIAgent agent2 = await provider.GetAgentAsync(agent2Id);
        // Assert
        Assert.Equal(agent2Id, agent2.Id);

        // Act & Assert
        await Assert.ThrowsAsync<RequestFailedException>(() => provider.GetAgentAsync(agentName));
    }

    private async ValueTask<string> CreateAgentAsync(string? name = null)
    {
        PersistentAgentsClient client = new(this.Configuration.Endpoint, new AzureCliCredential());
        PersistentAgent agent = await client.Administration.CreateAgentAsync(this.Configuration.DeploymentName, name: name);
        return agent.Id;
    }

    private AzureAIConfiguration Configuration
    {
        get
        {
            if (this._configuration is null)
            {
                this._configuration ??= InitializeConfig().GetSection("AzureAI").Get<AzureAIConfiguration>();
                Assert.NotNull(this._configuration);
            }

            return this._configuration;
        }
    }
}
