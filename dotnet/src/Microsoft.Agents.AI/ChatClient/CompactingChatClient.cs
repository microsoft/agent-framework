// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Runtime.CompilerServices;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Compaction;
using Microsoft.Extensions.AI;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI;

/// <summary>
/// A delegating <see cref="IChatClient"/> that applies an <see cref="ICompactionStrategy"/> to the message list
/// before each call to the inner chat client.
/// </summary>
/// <remarks>
/// <para>
/// This client is used for in-run compaction during the tool loop. It is inserted into the
/// <see cref="IChatClient"/> pipeline before the <see cref="FunctionInvokingChatClient"/> so that
/// compaction is applied before every LLM call, including those triggered by tool call iterations.
/// </para>
/// <para>
/// The compaction strategy organizes messages into atomic groups (preserving tool-call/result pairings)
/// before applying compaction logic. Only included messages are forwarded to the inner client.
/// </para>
/// </remarks>
internal sealed class CompactingChatClient : DelegatingChatClient
{
    private readonly ICompactionStrategy _compactionStrategy;

    /// <summary>
    /// Initializes a new instance of the <see cref="CompactingChatClient"/> class.
    /// </summary>
    /// <param name="innerClient">The inner chat client to delegate to.</param>
    /// <param name="compactionStrategy">The compaction strategy to apply before each call.</param>
    public CompactingChatClient(IChatClient innerClient, ICompactionStrategy compactionStrategy)
        : base(innerClient)
    {
        this._compactionStrategy = Throw.IfNull(compactionStrategy);
    }

    /// <inheritdoc/>
    public override async Task<ChatResponse> GetResponseAsync(
        IEnumerable<ChatMessage> messages,
        ChatOptions? options = null,
        CancellationToken cancellationToken = default)
    {
        List<ChatMessage> compactedMessages = await this.ApplyCompactionAsync(messages, cancellationToken).ConfigureAwait(false);
        return await base.GetResponseAsync(compactedMessages, options, cancellationToken).ConfigureAwait(false);
    }

    /// <inheritdoc/>
    public override async IAsyncEnumerable<ChatResponseUpdate> GetStreamingResponseAsync(
        IEnumerable<ChatMessage> messages,
        ChatOptions? options = null,
        [EnumeratorCancellation] CancellationToken cancellationToken = default)
    {
        List<ChatMessage> compactedMessages = await this.ApplyCompactionAsync(messages, cancellationToken).ConfigureAwait(false);
        await foreach (var update in base.GetStreamingResponseAsync(compactedMessages, options, cancellationToken).ConfigureAwait(false))
        {
            yield return update;
        }
    }

    private async Task<List<ChatMessage>> ApplyCompactionAsync(IEnumerable<ChatMessage> messages, CancellationToken cancellationToken)
    {
        List<ChatMessage> messageList = messages as List<ChatMessage> ?? [.. messages];
        MessageGroups groups = MessageGroups.Create(messageList);

        bool compacted = await this._compactionStrategy.CompactAsync(groups, cancellationToken).ConfigureAwait(false);

        return compacted ? [.. groups.GetIncludedMessages()] : messageList;
    }
}
