// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;
using AgentConversation.IntegrationTests;
using Microsoft.Agents.AI;
using Microsoft.Extensions.AI;
using Moq;

namespace Microsoft.Agents.AI.Abstractions.IntegrationTests;

/// <summary>
/// An example <see cref="IConversationTestSystem"/> that uses an in-memory mock <see cref="IChatClient"/>
/// so the harness can be exercised without live AI service credentials.
/// </summary>
/// <remarks>
/// In a real integration test against a live AI service (e.g., OpenAI Chat Completion), this class
/// would be replaced with an implementation that constructs <see cref="ChatClientAgent"/> instances
/// backed by the real <see cref="IChatClient"/>. The compaction contract can similarly be wired up
/// to an <see cref="Microsoft.Extensions.AI.IChatReducer"/> of your choice.
/// </remarks>
public sealed class InMemoryConversationTestSystem : IConversationTestSystem
{
    /// <summary>
    /// A deterministic response suffix appended by the mock chat client to every assistant reply.
    /// Test validations can assert on this value to confirm the mock was invoked.
    /// </summary>
    public const string MockResponseSuffix = "[mock-response]";

    /// <inheritdoc />
    public Task<AIAgent> CreateAgentAsync(
        ConversationAgentDefinition definition,
        CancellationToken cancellationToken = default)
    {
        // Create a mock IChatClient that returns a deterministic response.
        var mockClient = new Mock<IChatClient>();
        mockClient
            .Setup(c => c.GetResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions?>(),
                It.IsAny<CancellationToken>()))
            .ReturnsAsync(() => new ChatResponse(
                new ChatMessage(ChatRole.Assistant,
                    $"Here are today's specials: Clam Chowder, Cobb Salad, Chai Tea. {MockResponseSuffix}")));

        // GetService is called internally by the harness for metadata; return null for unknown types.
        mockClient
            .Setup(c => c.GetService(It.IsAny<System.Type>(), It.IsAny<object?>()))
            .Returns((System.Type _, object? _) => null);

        AIAgent agent = new ChatClientAgent(
            mockClient.Object,
            options: new ChatClientAgentOptions
            {
                Name = definition.Name,
                ChatOptions = new ChatOptions
                {
                    Instructions = definition.Instructions,
                    Tools = definition.Tools is not null ? new System.Collections.Generic.List<AITool>(definition.Tools) : null,
                }
            });

        return Task.FromResult(agent);
    }

    /// <inheritdoc />
    public Task<IList<ChatMessage>?> CompactAsync(
        IList<ChatMessage> messages,
        CancellationToken cancellationToken = default)
    {
        // No compaction in this example system.
        return Task.FromResult<IList<ChatMessage>?>(null);
    }
}
