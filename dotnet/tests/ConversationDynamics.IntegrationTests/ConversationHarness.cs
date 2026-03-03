// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.AI;
using Microsoft.Extensions.AI;

namespace ConversationDynamics.IntegrationTests;

/// <summary>
/// Orchestrates the execution of a <see cref="IConversationTestCase"/> against a given
/// <see cref="IConversationTestSystem"/>: restores the conversation context, optionally runs compaction,
/// executes each step, captures before/after metrics, and runs per-step validations.
/// </summary>
public sealed class ConversationHarness
{
    private readonly IConversationTestSystem _system;

    /// <summary>
    /// Initializes a new instance of <see cref="ConversationHarness"/>.
    /// </summary>
    /// <param name="system">The system under test that provides agent creation and compaction.</param>
    public ConversationHarness(IConversationTestSystem system)
    {
        if (system is null)
        {
            throw new ArgumentNullException(nameof(system));
        }

        this._system = system;
    }

    /// <summary>
    /// Runs the supplied <paramref name="testCase"/> from its serialized initial context, executing
    /// every <see cref="ConversationStep"/> in order and returning the combined metrics report.
    /// </summary>
    /// <param name="testCase">The test case to execute.</param>
    /// <param name="cancellationToken">A token to cancel the operation.</param>
    /// <returns>
    /// A <see cref="ConversationMetricsReport"/> describing the before-and-after state of the
    /// conversation context across all steps.
    /// </returns>
    /// <exception cref="ArgumentNullException"><paramref name="testCase"/> is <see langword="null"/>.</exception>
    /// <exception cref="InvalidOperationException">
    /// Thrown when a step references an agent name that is not present in <see cref="IConversationTestCase.AgentDefinitions"/>.
    /// </exception>
    public async Task<ConversationMetricsReport> RunAsync(
        IConversationTestCase testCase,
        CancellationToken cancellationToken = default)
    {
        if (testCase is null)
        {
            throw new ArgumentNullException(nameof(testCase));
        }

        // 1. Restore the initial context.
        var initialMessages = testCase.GetInitialMessages();

        // 2. Capture "before" metrics.
        var beforeMetrics = MeasureMetrics(initialMessages);

        // 3. Create the agents defined for this test case.
        var agents = new Dictionary<string, AIAgent>(StringComparer.Ordinal);
        foreach (var entry in testCase.AgentDefinitions)
        {
            agents[entry.Key] = await this._system.CreateAgentAsync(entry.Value, cancellationToken).ConfigureAwait(false);
        }

        // 4. Create sessions and restore the initial messages for each agent.
        var sessions = new Dictionary<string, AgentSession>(StringComparer.Ordinal);
        foreach (var entry in agents)
        {
            var session = await entry.Value.CreateSessionAsync(cancellationToken).ConfigureAwait(false);
            RestoreMessages(entry.Value, session, initialMessages);
            sessions[entry.Key] = session;
        }

        // 5. Optionally compact the messages.
        var compacted = await this._system.CompactAsync(initialMessages, cancellationToken).ConfigureAwait(false);
        if (compacted is not null)
        {
            // Apply the compacted history to all agent sessions.
            foreach (var entry in agents)
            {
                RestoreMessages(entry.Value, sessions[entry.Key], compacted);
            }
        }

        // 6. Execute each step.
        foreach (var step in testCase.Steps)
        {
            if (!agents.TryGetValue(step.AgentName, out var agent))
            {
                throw new InvalidOperationException(
                    $"Step references agent '{step.AgentName}' which is not defined in the test case. " +
                    $"Defined agents: {string.Join(", ", agents.Keys)}");
            }

            var session = sessions[step.AgentName];
            AgentResponse response;

            if (step.Input is not null)
            {
                response = await agent.RunAsync(step.Input, session, cancellationToken: cancellationToken).ConfigureAwait(false);
            }
            else
            {
                response = await agent.RunAsync(session, cancellationToken: cancellationToken).ConfigureAwait(false);
            }

            // 7. Capture "after" metrics for this step and run the step's validation.
            var currentMessages = GetCurrentMessages(agent, sessions[step.AgentName], initialMessages, compacted);
            var afterMetrics = MeasureMetrics(currentMessages);
            var metricsReport = new ConversationMetricsReport
            {
                Before = beforeMetrics,
                After = afterMetrics,
            };

            step.Validate?.Invoke(response, metricsReport);
        }

        // 8. Capture the final "after" metrics from the first agent's session.
        var firstAgent = agents.Values.First();
        var firstSession = sessions[agents.Keys.First()];
        var finalMessages = GetCurrentMessages(firstAgent, firstSession, initialMessages, compacted);
        var finalAfterMetrics = MeasureMetrics(finalMessages);

        return new ConversationMetricsReport
        {
            Before = beforeMetrics,
            After = finalAfterMetrics,
        };
    }

    /// <summary>
    /// Drives a conversation with the agents defined in <paramref name="testCase"/> to produce the initial
    /// context, then serializes that context to <paramref name="outputFilePath"/>.
    /// </summary>
    /// <remarks>
    /// This method should be called once (outside of normal test execution) to generate the fixture
    /// data that tests will subsequently restore via <see cref="IConversationTestCase.GetInitialMessages"/>.
    /// </remarks>
    /// <param name="testCase">The test case whose initial context should be created.</param>
    /// <param name="outputFilePath">The file path to write the serialized context to.</param>
    /// <param name="cancellationToken">A token to cancel the operation.</param>
    public async Task SerializeInitialContextAsync(
        IConversationTestCase testCase,
        string outputFilePath,
        CancellationToken cancellationToken = default)
    {
        if (testCase is null)
        {
            throw new ArgumentNullException(nameof(testCase));
        }

        if (string.IsNullOrEmpty(outputFilePath))
        {
            throw new ArgumentException("Output file path must not be null or empty.", nameof(outputFilePath));
        }

        // Create agents for context generation.
        var agents = new Dictionary<string, AIAgent>(StringComparer.Ordinal);
        foreach (var entry in testCase.AgentDefinitions)
        {
            agents[entry.Key] = await this._system.CreateAgentAsync(entry.Value, cancellationToken).ConfigureAwait(false);
        }

        var messages = await testCase.CreateInitialContextAsync(agents, cancellationToken).ConfigureAwait(false);
        ConversationContextSerializer.SaveToFile(outputFilePath, messages);
    }

    // -------------------------------------------------------------------------
    // Private helpers
    // -------------------------------------------------------------------------

    private static ConversationMetrics MeasureMetrics(IList<ChatMessage> messages)
    {
        var serialized = ConversationContextSerializer.Serialize(messages);
        return new ConversationMetrics
        {
            MessageCount = messages.Count,
            SerializedSizeBytes = System.Text.Encoding.UTF8.GetByteCount(serialized),
        };
    }

    private static void RestoreMessages(AIAgent agent, AgentSession session, IList<ChatMessage> messages)
    {
        // InMemoryChatHistoryProvider is the standard history provider for ChatClientAgent.
        // When found, load the messages directly into the provider's state for this session.
        if (agent.GetService<ChatHistoryProvider>() is InMemoryChatHistoryProvider memProvider)
        {
            memProvider.SetMessages(session, messages.ToList());
        }
    }

    private static IList<ChatMessage> GetCurrentMessages(
        AIAgent agent,
        AgentSession session,
        IList<ChatMessage> fallbackInitial,
        IList<ChatMessage>? compacted)
    {
        if (agent.GetService<ChatHistoryProvider>() is InMemoryChatHistoryProvider memProvider)
        {
            return memProvider.GetMessages(session);
        }

        // Fall back to the compacted (or original) initial messages when the provider is unavailable.
        return compacted ?? fallbackInitial;
    }
}
