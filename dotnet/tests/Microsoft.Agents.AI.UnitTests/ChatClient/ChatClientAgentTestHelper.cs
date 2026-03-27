// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.DependencyInjection;
using Moq;

namespace Microsoft.Agents.AI.UnitTests;

/// <summary>
/// Shared test helper for <see cref="ChatClientAgent"/> integration tests that verify
/// end-to-end behavior with <see cref="ChatHistoryPersistingChatClient"/> and
/// <see cref="FunctionInvokingChatClient"/>.
/// </summary>
internal static class ChatClientAgentTestHelper
{
    /// <summary>
    /// Represents an expected service call during a test: an optional input verifier and the response to return.
    /// </summary>
    /// <param name="Response">The <see cref="ChatResponse"/> the mock service should return for this call.</param>
    /// <param name="VerifyInput">Optional callback to verify the messages sent to the service on this call.</param>
#pragma warning disable CA1812 // Instantiated by test classes
    public sealed record ServiceCallExpectation(
        ChatResponse Response,
        Action<List<ChatMessage>>? VerifyInput = null);
#pragma warning restore CA1812

    /// <summary>
    /// Describes the expected shape of a message in the persisted history for structural comparison.
    /// </summary>
    /// <param name="Role">The expected role of the message.</param>
    /// <param name="TextContains">Optional substring that the message text should contain.</param>
    /// <param name="ContentTypes">Optional array of expected <see cref="AIContent"/> types in the message.</param>
#pragma warning disable CA1812 // Instantiated by test classes
    public sealed record ExpectedMessage(
        ChatRole Role,
        string? TextContains = null,
        Type[]? ContentTypes = null);
#pragma warning restore CA1812

    /// <summary>
    /// The result of a RunAsync invocation, containing the response, session, agent,
    /// captured service inputs, and call counts for detailed verification.
    /// </summary>
    public sealed record RunResult(
        AgentResponse Response,
        ChatClientAgentSession Session,
        ChatClientAgent Agent,
        Mock<IChatClient> MockService,
        int TotalServiceCalls,
        List<List<ChatMessage>> CapturedServiceInputs);

    /// <summary>
    /// Creates a mock <see cref="IChatClient"/> that returns responses in sequence,
    /// captures input messages, and optionally verifies inputs.
    /// </summary>
    /// <param name="expectations">The ordered sequence of expected service calls.</param>
    /// <param name="callIndex">Shared call index counter (allows reuse across multiple RunAsync calls).</param>
    /// <param name="capturedInputs">List that captured service inputs are appended to.</param>
    /// <returns>The configured mock.</returns>
    public static Mock<IChatClient> CreateSequentialMock(
        List<ServiceCallExpectation> expectations,
        Ref<int> callIndex,
        List<List<ChatMessage>> capturedInputs)
    {
        Mock<IChatClient> mock = new();
        mock.Setup(s => s.GetResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>()))
            .Returns<IEnumerable<ChatMessage>, ChatOptions?, CancellationToken>((msgs, _, _) =>
            {
                int idx = callIndex.Value++;
                var messageList = msgs.ToList();
                capturedInputs.Add(messageList);

                if (idx >= expectations.Count)
                {
                    throw new InvalidOperationException(
                        $"Mock received unexpected service call #{idx + 1}. Only {expectations.Count} call(s) were expected.");
                }

                var expectation = expectations[idx];
                expectation.VerifyInput?.Invoke(messageList);
                return Task.FromResult(expectation.Response);
            });
        return mock;
    }

    /// <summary>
    /// Runs the agent with the given inputs, automatically verifying service call count
    /// and optional expected history, and returns the result for further assertions.
    /// </summary>
    /// <param name="inputMessages">Messages to pass to RunAsync.</param>
    /// <param name="serviceCallExpectations">Ordered service call expectations for the mock.</param>
    /// <param name="agentOptions">Options for configuring the agent. If null, defaults are used.</param>
    /// <param name="existingSession">An existing session to reuse (for multi-turn tests). If null, a new session is created.</param>
    /// <param name="existingAgent">An existing agent to reuse (for multi-turn tests). If null, a new agent is created.</param>
    /// <param name="existingMock">An existing mock to reuse (for multi-turn tests). If null, a new mock is created.</param>
    /// <param name="callIndex">Shared call index for multi-turn tests. If null, a new counter is created.</param>
    /// <param name="capturedInputs">Shared captured inputs list for multi-turn tests. If null, a new list is created.</param>
    /// <param name="initialChatHistory">Optional initial chat history to pre-populate in <see cref="InMemoryChatHistoryProvider"/>.</param>
    /// <param name="runOptions">Optional <see cref="AgentRunOptions"/> to pass to RunAsync.</param>
    /// <param name="expectedServiceCallCount">
    /// If provided, asserts the total number of service calls matches.
    /// For multi-turn tests, pass null and verify after the final turn.
    /// </param>
    /// <param name="expectedHistory">
    /// If provided, asserts that the persisted history matches these expected messages.
    /// For multi-turn tests, pass null and verify after the final turn.
    /// </param>
    /// <returns>A <see cref="RunResult"/> containing the response, session, agent, mock, and captured inputs.</returns>
    public static async Task<RunResult> RunAsync(
        List<ChatMessage> inputMessages,
        List<ServiceCallExpectation> serviceCallExpectations,
        ChatClientAgentOptions? agentOptions = null,
        ChatClientAgentSession? existingSession = null,
        ChatClientAgent? existingAgent = null,
        Mock<IChatClient>? existingMock = null,
        Ref<int>? callIndex = null,
        List<List<ChatMessage>>? capturedInputs = null,
        List<ChatMessage>? initialChatHistory = null,
        AgentRunOptions? runOptions = null,
        int? expectedServiceCallCount = null,
        List<ExpectedMessage>? expectedHistory = null)
    {
        callIndex ??= new Ref<int>(0);
        capturedInputs ??= [];
        var mock = existingMock ?? CreateSequentialMock(serviceCallExpectations, callIndex, capturedInputs);
        agentOptions ??= new ChatClientAgentOptions();

        var agent = existingAgent ?? new ChatClientAgent(
            mock.Object,
            options: agentOptions,
            services: new ServiceCollection().BuildServiceProvider());

        var session = existingSession ?? (await agent.CreateSessionAsync() as ChatClientAgentSession)!;

        // Pre-populate initial chat history if provided.
        if (initialChatHistory is not null)
        {
            (agent.ChatHistoryProvider as InMemoryChatHistoryProvider)
                ?.SetMessages(session, new List<ChatMessage>(initialChatHistory));
        }

        var response = await agent.RunAsync(inputMessages, session, runOptions);

        var result = new RunResult(response, session, agent, mock, callIndex.Value, capturedInputs);

        // Auto-verify service call count if specified.
        if (expectedServiceCallCount.HasValue)
        {
            Assert.Equal(expectedServiceCallCount.Value, callIndex.Value);
        }

        // Auto-verify persisted history if specified.
        if (expectedHistory is not null)
        {
            var history = GetPersistedHistory(agent, session);
            AssertMessagesMatch(history, expectedHistory);
        }

        return result;
    }

    /// <summary>
    /// Asserts that the actual message list matches the expected message patterns structurally.
    /// Checks message count, roles, optional text content, and optional content types.
    /// </summary>
    /// <param name="actual">The actual messages to verify.</param>
    /// <param name="expected">The expected message patterns.</param>
    public static void AssertMessagesMatch(List<ChatMessage> actual, List<ExpectedMessage> expected)
    {
        Assert.True(
            expected.Count == actual.Count,
            $"Expected {expected.Count} message(s) but found {actual.Count}.\nActual messages:\n{FormatMessages(actual)}");

        for (int i = 0; i < expected.Count; i++)
        {
            var exp = expected[i];
            var act = actual[i];

            Assert.True(
                exp.Role == act.Role,
                $"Message [{i}]: expected role {exp.Role} but found {act.Role}.\nActual messages:\n{FormatMessages(actual)}");

            if (exp.TextContains is not null)
            {
                Assert.Contains(exp.TextContains, act.Text, StringComparison.Ordinal);
            }

            if (exp.ContentTypes is not null)
            {
                AssertContentTypes(act.Contents, exp.ContentTypes, i);
            }
        }
    }

    /// <summary>
    /// Gets the persisted chat history from the agent's <see cref="InMemoryChatHistoryProvider"/>.
    /// </summary>
    /// <param name="agent">The agent whose history provider to query.</param>
    /// <param name="session">The session to get history for.</param>
    /// <returns>The list of persisted messages, or an empty list if no provider is available.</returns>
    public static List<ChatMessage> GetPersistedHistory(ChatClientAgent agent, AgentSession session)
    {
        var provider = agent.ChatHistoryProvider as InMemoryChatHistoryProvider;
        return provider?.GetMessages(session) ?? [];
    }

    /// <summary>
    /// Formats the contents of a message list as a diagnostic string for test failure messages.
    /// </summary>
    /// <param name="messages">The messages to format.</param>
    /// <returns>A human-readable representation of the messages.</returns>
    public static string FormatMessages(IEnumerable<ChatMessage> messages)
    {
        var sb = new StringBuilder();
        int index = 0;
        foreach (var msg in messages)
        {
            sb.AppendLine($"  [{index}] Role={msg.Role}, Text=\"{msg.Text}\", Contents=[{string.Join(", ", msg.Contents.Select(c => c.GetType().Name))}]");
            index++;
        }

        return sb.ToString();
    }

    /// <summary>
    /// A simple mutable reference wrapper for value types, allowing shared state across callbacks.
    /// </summary>
    public sealed class Ref<T>(T value) where T : struct
    {
        public T Value { get; set; } = value;
    }

    /// <summary>
    /// Asserts that a message's content collection contains the expected content types.
    /// </summary>
    private static void AssertContentTypes(IList<AIContent> contents, Type[] expectedTypes, int messageIndex)
    {
        Assert.True(
            contents.Count >= expectedTypes.Length,
            $"Message [{messageIndex}]: expected at least {expectedTypes.Length} content(s) but found {contents.Count}. " +
            $"Actual types: [{string.Join(", ", contents.Select(c => c.GetType().Name))}]");

        foreach (var expectedType in expectedTypes)
        {
            Assert.True(
                contents.Any(c => expectedType.IsInstanceOfType(c)),
                $"Message [{messageIndex}]: expected content of type {expectedType.Name} but found [{string.Join(", ", contents.Select(c => c.GetType().Name))}]");
        }
    }
}
