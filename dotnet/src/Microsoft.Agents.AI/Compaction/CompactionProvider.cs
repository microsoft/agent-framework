// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Diagnostics.CodeAnalysis;
using System.Text.Json.Serialization;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using Microsoft.Shared.DiagnosticIds;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI.Compaction;

/// <summary>
/// A <see cref="MessageAIContextProvider"/> that applies a <see cref="CompactionStrategy"/> to compact
/// the message list before each agent invocation.
/// </summary>
/// <remarks>
/// <para>
/// This provider performs in-run compaction by organizing messages into atomic groups (preserving
/// tool-call/result pairings) before applying compaction logic. Only included messages are forwarded
/// to the agent's underlying chat client.
/// </para>
/// <para>
/// The <see cref="CompactionProvider"/> can be added to an agent's context provider pipeline
/// via <see cref="ChatClientAgentOptions.AIContextProviders"/> or via <c>UseAIContextProviders</c>
/// on a <see cref="ChatClientBuilder"/> or <see cref="AIAgentBuilder"/>.
/// </para>
/// </remarks>
[Experimental(DiagnosticIds.Experiments.AgentsAIExperiments)]
public sealed class CompactionProvider : AIContextProvider
{
    private readonly CompactionStrategy _compactionStrategy;
    private readonly ProviderSessionState<State> _sessionState;

    /// <summary>
    /// Initializes a new instance of the <see cref="CompactionProvider"/> class.
    /// </summary>
    /// <param name="compactionStrategy">The compaction strategy to apply before each invocation.</param>
    /// <param name="stateKey">
    /// An optional key used to store the provider state in the <see cref="AgentSession.StateBag"/>.
    /// </param>
    /// <exception cref="ArgumentNullException"><paramref name="compactionStrategy"/> is <see langword="null"/>.</exception>
    public CompactionProvider(CompactionStrategy compactionStrategy, string? stateKey = null)
    {
        this._compactionStrategy = Throw.IfNull(compactionStrategy);
        stateKey ??= $"{nameof(CompactionProvider)}:{Convert.ToBase64String(BitConverter.GetBytes(compactionStrategy.GetHashCode()))}";
        this.StateKeys = [stateKey];
        this._sessionState = new ProviderSessionState<State>(
            _ => new State(),
            stateKey,
            AgentJsonUtilities.DefaultOptions);
    }

    /// <inheritdoc />
    public override IReadOnlyList<string> StateKeys { get; }

    /// <summary>
    /// Applies compaction strategy to the provided message list and returns the compacted messages.
    /// This can be used for ad-hoc compaction outside of the provider pipeline.
    /// </summary>
    /// <param name="compactionStrategy">The compaction strategy to apply before each invocation.</param>
    /// <param name="messages">The messages to compact</param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests.</param>
    /// <returns></returns>
    public static async Task<IEnumerable<ChatMessage>> CompactAsync(CompactionStrategy compactionStrategy, IEnumerable<ChatMessage> messages, CancellationToken cancellationToken = default)
    {
        Throw.IfNull(compactionStrategy);
        Throw.IfNull(messages);

        List<ChatMessage> messageList = messages as List<ChatMessage> ?? [.. messages];
        MessageIndex messageIndex = MessageIndex.Create(messageList);

        await compactionStrategy.CompactAsync(messageIndex, cancellationToken).ConfigureAwait(false);

        return messageIndex.GetIncludedMessages();
    }

    /// <summary>
    /// Applies the compaction strategy to the accumulated message list before forwarding it to the agent.
    /// </summary>
    /// <param name="context">Contains the request context including all accumulated messages.</param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests.</param>
    /// <returns>
    /// A task that represents the asynchronous operation. The task result contains an <see cref="AIContext"/>
    /// with the compacted message list. If no compaction was needed, the original context is returned unchanged.
    /// </returns>
    protected override async ValueTask<AIContext> InvokingCoreAsync(InvokingContext context, CancellationToken cancellationToken = default)
    {
        AgentSession? session = context.Session;
        IEnumerable<ChatMessage>? allMessages = context.AIContext.Messages;

        if (session is null || allMessages is null)
        {
            // No session available or no messages — pass through unchanged.
            return context.AIContext;
        }

        ChatClientAgentSession? chatClientSession = session.GetService<ChatClientAgentSession>();
        if (chatClientSession is not null &&
            !string.IsNullOrWhiteSpace(chatClientSession.ConversationId))
        {
            // Session is managed by remote service
            return context.AIContext;
        }

        List<ChatMessage> messageList = allMessages as List<ChatMessage> ?? [.. allMessages];

        State state = this._sessionState.GetOrInitializeState(session);

        MessageIndex messageIndex;
        if (state.MessageGroups.Count > 0)
        {
            // Update existing index with any new messages appended since the last call.
            messageIndex = new(state.MessageGroups);
            messageIndex.Update(messageList);
        }
        else
        {
            // First pass — initialize the message index from scratch.
            messageIndex = MessageIndex.Create(messageList);
        }

        // Apply compaction
        await this._compactionStrategy.CompactAsync(messageIndex, cancellationToken).ConfigureAwait(false);

        // Persist the index
        state.MessageGroups.Clear();
        state.MessageGroups.AddRange(messageIndex.Groups);

        return new AIContext
        {
            Instructions = context.AIContext.Instructions,
            Messages = messageIndex.GetIncludedMessages(),
            Tools = context.AIContext.Tools
        };
    }

    /// <summary>
    /// Represents the persisted state of a <see cref="CompactionProvider"/> stored in the <see cref="AgentSession.StateBag"/>.
    /// </summary>
    internal sealed class State
    {
        /// <summary>
        /// Gets or sets the message index groups used for incremental compaction updates.
        /// </summary>
        [JsonPropertyName("messagegroups")]
        public List<MessageGroup> MessageGroups { get; set; } = [];
    }
}
