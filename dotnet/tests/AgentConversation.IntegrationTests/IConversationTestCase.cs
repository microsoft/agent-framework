// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.AI;
using Microsoft.Extensions.AI;

namespace AgentConversation.IntegrationTests;

/// <summary>
/// Defines a single agent conversation test case.
/// </summary>
/// <remarks>
/// Each test case describes the initial conversation context (as a list of <see cref="ChatMessage"/> instances),
/// the agents that participate in the conversation, the steps to execute, and the expected outcomes.
/// The initial context can either be loaded from a previously serialized file or generated on-demand
/// via <see cref="CreateInitialContextAsync"/>.
/// </remarks>
public interface IConversationTestCase
{
    /// <summary>
    /// Gets the human-readable name that uniquely identifies this test case.
    /// </summary>
    string Name { get; }

    /// <summary>
    /// Gets the agents involved in this test case, keyed by their names.
    /// Each entry is a <see cref="ConversationAgentDefinition"/> that describes how to create the agent.
    /// </summary>
    IReadOnlyDictionary<string, ConversationAgentDefinition> AgentDefinitions { get; }

    /// <summary>
    /// Returns the initial list of <see cref="ChatMessage"/> instances to restore into the conversation
    /// context before any steps are executed.
    /// </summary>
    /// <returns>
    /// The initial chat messages. These are typically loaded from a previously serialized JSON file
    /// produced by <see cref="CreateInitialContextAsync"/>.
    /// </returns>
    IList<ChatMessage> GetInitialMessages();

    /// <summary>
    /// Gets the ordered list of steps to execute against the restored conversation context.
    /// </summary>
    IReadOnlyList<ConversationStep> Steps { get; }

    /// <summary>
    /// Creates the initial conversation context by actually driving a conversation with the provided agents,
    /// then returns the resulting list of messages.
    /// </summary>
    /// <remarks>
    /// This method is intended to be called once (e.g., during a setup phase) to produce the serialized
    /// context that subsequent test runs will deserialize. Implementations should build up a long or
    /// complex conversation that is representative of the long-running operation scenario being validated.
    /// </remarks>
    /// <param name="agents">
    /// The agents to use when building the initial context, keyed by their names as defined in
    /// <see cref="AgentDefinitions"/>.
    /// </param>
    /// <param name="cancellationToken">A token to cancel the operation.</param>
    /// <returns>
    /// The ordered list of <see cref="ChatMessage"/> instances that form the initial context.
    /// </returns>
    Task<IList<ChatMessage>> CreateInitialContextAsync(
        IReadOnlyDictionary<string, AIAgent> agents,
        CancellationToken cancellationToken = default);
}
