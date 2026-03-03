// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.AI;
using Microsoft.Extensions.AI;

namespace ConversationDynamics.IntegrationTests;

/// <summary>
/// Abstracts the system-specific concerns of a conversation dynamics test run: how agents are created
/// and how context compaction is performed.
/// </summary>
/// <remarks>
/// Implement this interface to adapt the <see cref="ConversationHarness"/> to a particular AI backend
/// (e.g., OpenAI Chat Completion, Azure AI, OpenAI Responses API). Each implementation controls:
/// <list type="bullet">
/// <item><description>
/// How <see cref="ConversationAgentDefinition"/> instances are turned into live <see cref="AIAgent"/> objects.
/// </description></item>
/// <item><description>
/// How context compaction is applied to a list of messages. Compaction is optional; returning
/// <see langword="null"/> means no compaction is performed.
/// </description></item>
/// </list>
/// </remarks>
public interface IConversationTestSystem
{
    /// <summary>
    /// Creates a live <see cref="AIAgent"/> from the supplied <paramref name="definition"/>.
    /// </summary>
    /// <param name="definition">The definition describing the agent to create.</param>
    /// <param name="cancellationToken">A token to cancel the operation.</param>
    /// <returns>A fully-initialised <see cref="AIAgent"/> ready to participate in the conversation.</returns>
    Task<AIAgent> CreateAgentAsync(
        ConversationAgentDefinition definition,
        CancellationToken cancellationToken = default);

    /// <summary>
    /// Optionally compacts (reduces) the supplied <paramref name="messages"/>.
    /// </summary>
    /// <param name="messages">The current list of messages to compact.</param>
    /// <param name="cancellationToken">A token to cancel the operation.</param>
    /// <returns>
    /// The compacted list of messages, or <see langword="null"/> if no compaction was performed.
    /// When <see langword="null"/> is returned the original <paramref name="messages"/> list is used unchanged.
    /// </returns>
    Task<IList<ChatMessage>?> CompactAsync(
        IList<ChatMessage> messages,
        CancellationToken cancellationToken = default);
}
