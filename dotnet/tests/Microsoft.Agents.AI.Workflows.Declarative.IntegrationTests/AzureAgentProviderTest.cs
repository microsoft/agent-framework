// Copyright (c) Microsoft. All rights reserved.

using System.Linq;
using System.Threading.Tasks;
using Azure.Identity;
using Microsoft.Agents.AI.Workflows.Declarative.IntegrationTests.Framework;
using Microsoft.Extensions.AI;
using Xunit.Abstractions;

namespace Microsoft.Agents.AI.Workflows.Declarative.IntegrationTests;

public sealed class AzureAgentProviderTest(ITestOutputHelper output) : IntegrationTest(output)
{
    [Fact]
    public async Task ConversationTestAsync()
    {
        // Arrange
        AzureAgentProvider provider = new(this.TestEndpoint, new AzureCliCredential());
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
}
