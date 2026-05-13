// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;
using AgentConversation.IntegrationTests;
using Microsoft.Agents.AI;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Abstractions.IntegrationTests;

/// <summary>
/// An example <see cref="IConversationTestCase"/> that validates the harness can restore a
/// pre-built conversation context and solicit a response from an agent.
/// </summary>
/// <remarks>
/// This test case uses a fixed, in-memory conversation representing a menu-ordering interaction.
/// The messages are defined inline (no JSON fixture file is required), which makes this a
/// self-contained example that runs without live AI credentials.
/// </remarks>
public sealed class MenuConversationTestCase : IConversationTestCase
{
    private const string AgentKey = "MenuAgent";

    /// <inheritdoc />
    public string Name => "MenuConversation";

    /// <inheritdoc />
    public IReadOnlyDictionary<string, ConversationAgentDefinition> AgentDefinitions { get; } =
        new Dictionary<string, ConversationAgentDefinition>
        {
            [AgentKey] = new ConversationAgentDefinition
            {
                Name = AgentKey,
                Instructions = "You are a helpful restaurant assistant. Answer questions about the menu.",
                Tools =
                [
                    AIFunctionFactory.Create(MenuTools.GetSpecials),
                    AIFunctionFactory.Create(MenuTools.GetItemPrice),
                ]
            }
        };

    /// <inheritdoc />
    public IReadOnlyList<ConversationStep> Steps { get; } =
    [
        new ConversationStep
        {
            AgentName = AgentKey,
            Input = new ChatMessage(ChatRole.User, "What are the specials today?"),
            Validate = (response, metrics) =>
            {
                Assert.NotNull(response);
                Assert.NotEmpty(response.Text);
                Assert.True(metrics.After.MessageCount > metrics.Before.MessageCount,
                    "Message count should grow after the step.");
            }
        }
    ];

    /// <inheritdoc />
    public IList<ChatMessage> GetInitialMessages() =>
        // A short, representative conversation context that is already in memory.
        [
            new ChatMessage(ChatRole.User, "Hello, I'd like to see the menu."),
            new ChatMessage(ChatRole.Assistant, "Welcome! I'm happy to help you with our menu. Feel free to ask about today's specials or the price of any item."),
        ];

    /// <inheritdoc />
    public async Task<IList<ChatMessage>> CreateInitialContextAsync(
        IReadOnlyDictionary<string, AIAgent> agents,
        CancellationToken cancellationToken = default)
    {
        // Build the initial context by running a short greeting exchange.
        var agent = agents[AgentKey];
        var session = await agent.CreateSessionAsync(cancellationToken).ConfigureAwait(false);

        await agent.RunAsync(
            new ChatMessage(ChatRole.User, "Hello, I'd like to see the menu."),
            session,
            cancellationToken: cancellationToken).ConfigureAwait(false);

        var historyProvider = agent.GetService<ChatHistoryProvider>() as InMemoryChatHistoryProvider;
        if (historyProvider is not null)
        {
            return historyProvider.GetMessages(session);
        }

        return GetInitialMessages();
    }
}
