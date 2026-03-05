// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Runtime.CompilerServices;
using System.Text.Json.Serialization;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI.Compaction;

/// <summary>
/// A delegating <see cref="IChatClient"/> that applies an <see cref="CompactionStrategy"/> to the message list
/// before each call to the inner chat client.
/// </summary>
/// <remarks>
/// <para>
/// This client is used for in-run compaction during the tool loop. It is inserted into the
/// <see cref="IChatClient"/> pipeline before the `FunctionInvokingChatClient` so that
/// compaction is applied before every LLM call, including those triggered by tool call iterations.
/// </para>
/// <para>
/// The compaction strategy organizes messages into atomic groups (preserving tool-call/result pairings)
/// before applying compaction logic. Only included messages are forwarded to the inner client.
/// </para>
/// </remarks>
internal sealed class CompactingChatClient : DelegatingChatClient
{
    private readonly CompactionStrategy _compactionStrategy;
    private readonly ProviderSessionState<State> _sessionState;

    /// <summary>
    /// Initializes a new instance of the <see cref="CompactingChatClient"/> class.
    /// </summary>
    /// <param name="innerClient">The inner chat client to delegate to.</param>
    /// <param name="compactionStrategy">The compaction strategy to apply before each call.</param>
    public CompactingChatClient(IChatClient innerClient, CompactionStrategy compactionStrategy)
        : base(innerClient)
    {
        this._compactionStrategy = Throw.IfNull(compactionStrategy);
        this._sessionState = new ProviderSessionState<State>(
            _ => new State(),
            Convert.ToBase64String(BitConverter.GetBytes(compactionStrategy.GetHashCode())),
            AgentJsonUtilities.DefaultOptions);
    }

    /// <inheritdoc/>
    public override async Task<ChatResponse> GetResponseAsync(
        IEnumerable<ChatMessage> messages,
        ChatOptions? options = null,
        CancellationToken cancellationToken = default)
    {
        IEnumerable<ChatMessage> compactedMessages = await this.ApplyCompactionAsync(messages, cancellationToken).ConfigureAwait(false);
        return await base.GetResponseAsync(compactedMessages, options, cancellationToken).ConfigureAwait(false);
    }

    /// <inheritdoc/>
    public override async IAsyncEnumerable<ChatResponseUpdate> GetStreamingResponseAsync(
        IEnumerable<ChatMessage> messages,
        ChatOptions? options = null,
        [EnumeratorCancellation] CancellationToken cancellationToken = default)
    {
        IEnumerable<ChatMessage> compactedMessages = await this.ApplyCompactionAsync(messages, cancellationToken).ConfigureAwait(false);
        await foreach (ChatResponseUpdate update in base.GetStreamingResponseAsync(compactedMessages, options, cancellationToken).ConfigureAwait(false))
        {
            yield return update;
        }
    }

    /// <inheritdoc />
    public override object? GetService(Type serviceType, object? serviceKey = null)
    {
        Throw.IfNull(serviceType);

        return
            serviceKey is null && serviceType.IsInstanceOfType(typeof(CompactionStrategy)) ?
                this._compactionStrategy :
                base.GetService(serviceType, serviceKey);
    }

    private async Task<IEnumerable<ChatMessage>> ApplyCompactionAsync(
        IEnumerable<ChatMessage> messages, CancellationToken cancellationToken)
    {
        List<ChatMessage> messageList = messages as List<ChatMessage> ?? [.. messages]; // %%% TODO - LIST COPY

        AgentRunContext? currentAgentContext = AIAgent.CurrentRunContext;
        if (currentAgentContext is null ||
            currentAgentContext.Session is null)
        {
            // No session available — no reason to compact
            return messages;
        }

        State state = this._sessionState.GetOrInitializeState(currentAgentContext.Session);

        MessageIndex messageIndex;
        if (state.MessageIndex.Count > 0)
        {
            // Update existing index
            messageIndex = new(state.MessageIndex);
            messageIndex.Update(messageList);
        }
        else
        {
            // First pass — initialize message index state
            messageIndex = MessageIndex.Create(messageList);
        }

        // Apply compaction
        Stopwatch stopwatch = Stopwatch.StartNew();
        bool wasCompacted = await this._compactionStrategy.CompactAsync(messageIndex, cancellationToken).ConfigureAwait(false);
        stopwatch.Stop();

        Debug.WriteLine($"COMPACTION: {wasCompacted} - {stopwatch.ElapsedMilliseconds}ms");

        if (wasCompacted)
        {
            state.MessageIndex = [.. messageIndex.Groups]; // %%% TODO - LIST COPY
        }

        return wasCompacted ? messageIndex.GetIncludedMessages() : messageList;
    }

    /// <summary>
    /// Represents the state of a <see cref="InMemoryChatHistoryProvider"/> stored in the <see cref="AgentSession.StateBag"/>.
    /// </summary>
    public sealed class State
    {
        /// <summary>
        /// Gets or sets the message index.
        /// </summary>
        [JsonPropertyName("messages")]
        public List<MessageGroup> MessageIndex { get; set; } = [];
    }
}
