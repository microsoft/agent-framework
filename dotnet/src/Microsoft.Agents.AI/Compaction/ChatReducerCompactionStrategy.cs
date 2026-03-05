// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Diagnostics.CodeAnalysis;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using Microsoft.Shared.DiagnosticIds;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI.Compaction;

/// <summary>
/// A compaction strategy that delegates to an <see cref="IChatReducer"/> to reduce the conversation's
/// included messages.
/// </summary>
/// <remarks>
/// <para>
/// This strategy bridges the <see cref="IChatReducer"/> abstraction from <c>Microsoft.Extensions.AI</c>
/// into the compaction pipeline. It collects the currently included messages from the
/// <see cref="MessageIndex"/>, passes them to the reducer, and rebuilds the index from the
/// reduced message list when the reducer produces fewer messages.
/// </para>
/// <para>
/// The <see cref="CompactionTrigger"/> controls when reduction is attempted.
/// Use <see cref="CompactionTriggers"/> for common trigger conditions such as token or message thresholds.
/// </para>
/// <para>
/// Use this strategy when you have an existing <see cref="IChatReducer"/> implementation
/// (such as <c>MessageCountingChatReducer</c>) and want to apply it as part of a
/// <see cref="CompactionStrategy"/> pipeline or as an in-run compaction strategy.
/// </para>
/// </remarks>
[Experimental(DiagnosticIds.Experiments.AgentsAIExperiments)]
public sealed class ChatReducerCompactionStrategy : CompactionStrategy
{
    /// <summary>
    /// Initializes a new instance of the <see cref="ChatReducerCompactionStrategy"/> class.
    /// </summary>
    /// <param name="chatReducer">
    /// The <see cref="IChatReducer"/> that performs the message reduction.
    /// </param>
    /// <param name="trigger">
    /// The <see cref="CompactionTrigger"/> that controls when compaction proceeds.
    /// </param>
    /// <param name="target">
    /// An optional target condition that controls when compaction stops. When <see langword="null"/>,
    /// defaults to the inverse of the <paramref name="trigger"/> — compaction stops as soon as the trigger would no longer fire.
    /// Note that the <see cref="IChatReducer"/> performs reduction in a single call, so the target is
    /// not evaluated incrementally; it is available for composition with other strategies via
    /// <see cref="PipelineCompactionStrategy"/>.
    /// </param>
    public ChatReducerCompactionStrategy(IChatReducer chatReducer, CompactionTrigger trigger, CompactionTrigger? target = null)
        : base(trigger, target)
    {
        this.ChatReducer = Throw.IfNull(chatReducer);
    }

    /// <summary>
    /// Gets the chat reducer used to reduce messages.
    /// </summary>
    public IChatReducer ChatReducer { get; }

    /// <inheritdoc/>
    protected override async Task<bool> ApplyCompactionAsync(MessageIndex index, CancellationToken cancellationToken)
    {
        List<ChatMessage> includedMessages = [.. index.GetIncludedMessages()];
        if (includedMessages.Count == 0)
        {
            return false;
        }

        IEnumerable<ChatMessage> reduced = await this.ChatReducer.ReduceAsync(includedMessages, cancellationToken).ConfigureAwait(false);
        IList<ChatMessage> reducedMessages = reduced as IList<ChatMessage> ?? [.. reduced];

        if (reducedMessages.Count >= includedMessages.Count)
        {
            return false;
        }

        // Rebuild the index from the reduced messages
        MessageIndex rebuilt = MessageIndex.Create(reducedMessages, index.Tokenizer);
        index.Groups.Clear();
        foreach (MessageGroup group in rebuilt.Groups)
        {
            index.Groups.Add(group);
        }

        return true;
    }
}
