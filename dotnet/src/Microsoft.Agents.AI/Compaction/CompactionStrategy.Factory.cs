// Copyright (c) Microsoft. All rights reserved.

using System;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Compaction;

/// <summary>
/// Base class for strategies that compact a <see cref="CompactionMessageIndex"/> to reduce context size.
/// </summary>
/// <remarks>
/// <para>
/// Compaction strategies operate on <see cref="CompactionMessageIndex"/> instances, which organize messages
/// into atomic groups that respect the tool-call/result pairing constraint. Strategies mutate the collection
/// in place by marking groups as excluded, removing groups, or replacing message content (e.g., with summaries).
/// </para>
/// <para>
/// Every strategy requires a <see cref="CompactionTrigger"/> that determines whether compaction should
/// proceed based on current <see cref="CompactionMessageIndex"/> metrics (token count, message count, turn count, etc.).
/// The base class evaluates this trigger at the start of <see cref="CompactAsync"/> and skips compaction when
/// the trigger returns <see langword="false"/>.
/// </para>
/// <para>
/// An optional <b>target</b> condition controls when compaction stops. Strategies incrementally exclude
/// groups and re-evaluate the target after each exclusion, stopping as soon as the target returns
/// <see langword="true"/>. When no target is specified, it defaults to the inverse of the trigger —
/// meaning compaction stops when the trigger condition would no longer fire.
/// </para>
/// <para>
/// Strategies can be applied at three lifecycle points:
/// <list type="bullet">
/// <item><description><b>In-run</b>: During the tool loop, before each LLM call, to keep context within token limits.</description></item>
/// <item><description><b>Pre-write</b>: Before persisting messages to storage via <see cref="ChatHistoryProvider"/>.</description></item>
/// <item><description><b>On existing storage</b>: As a maintenance operation to compact stored history.</description></item>
/// </list>
/// </para>
/// <para>
/// Multiple strategies can be composed by applying them sequentially to the same <see cref="CompactionMessageIndex"/>
/// via <see cref="PipelineCompactionStrategy"/>.
/// </para>
/// </remarks>
public abstract partial class CompactionStrategy
{
    /// <summary>
    /// Creates a pre-configured <see cref="CompactionStrategy"/> from a combination of
    /// <paramref name="approach"/> and <paramref name="size"/>.
    /// </summary>
    /// <remarks>
    /// <para>
    /// The <paramref name="approach"/> controls which strategies are included in the pipeline:
    /// <list type="bullet">
    /// <item><description><see cref="CompactionApproach.Gentle"/>: tool result collapsing + truncation backstop. No <paramref name="chatClient"/> required.</description></item>
    /// <item><description><see cref="CompactionApproach.Balanced"/>: tool result collapsing + LLM summarization + truncation backstop.</description></item>
    /// <item><description><see cref="CompactionApproach.Aggressive"/>: tool result collapsing + LLM summarization + sliding window + truncation backstop.</description></item>
    /// </list>
    /// </para>
    /// <para>
    /// The <paramref name="size"/> controls the token and message thresholds at which each stage triggers.
    /// Choose a size that matches the input token limit of your model.
    /// </para>
    /// </remarks>
    /// <param name="approach">
    /// The compaction approach that controls which strategy or pipeline to use.
    /// </param>
    /// <param name="size">
    /// The context-size profile that controls token and message thresholds.
    /// </param>
    /// <param name="chatClient">
    /// The <see cref="IChatClient"/> used for LLM-based summarization.
    /// </param>
    /// <returns>A <see cref="CompactionStrategy"/> configured for the specified approach and size.</returns>
    /// <exception cref="ArgumentNullException">
    /// <paramref name="chatClient"/> is <see langword="null"/> and <paramref name="approach"/> requires one.
    /// </exception>
    /// <exception cref="ArgumentOutOfRangeException">
    /// <paramref name="approach"/> or <paramref name="size"/> is not a defined enum value.
    /// </exception>
    public static CompactionStrategy Create(CompactionApproach approach, CompactionSize size, IChatClient chatClient)
    {
        int tokenLimit = GetTokenCountLimit(size);
        int messageLimit = GetMessageCountLimit(size);

        return approach switch
        {
            CompactionApproach.Gentle => CreateGentlePipeline(tokenLimit, messageLimit, chatClient),
            CompactionApproach.Balanced => CreateBalancedPipeline(tokenLimit, messageLimit, chatClient),
            CompactionApproach.Aggressive => CreateAggressivePipeline(tokenLimit, messageLimit, GetTurnCountLimit(size), chatClient),
            _ => throw new ArgumentOutOfRangeException(nameof(approach), approach, null),
        };
    }

    private static int GetTokenCountLimit(CompactionSize size) => size switch
    {
        CompactionSize.Compact => 0x1FFF,  // 8k
        CompactionSize.Moderate => 0x7FFF, // 32k
        CompactionSize.Generous => 0xFFFF, // 64k
        _ => throw new ArgumentOutOfRangeException(nameof(size), size, null),
    };

    private static int GetMessageCountLimit(CompactionSize size) => size switch
    {
        CompactionSize.Compact => 50,
        CompactionSize.Moderate => 500,
        CompactionSize.Generous => 1000,
        _ => throw new ArgumentOutOfRangeException(nameof(size), size, null),
    };

    private static int GetTurnCountLimit(CompactionSize size) => size switch
    {
        CompactionSize.Compact => 25,
        CompactionSize.Moderate => 250,
        CompactionSize.Generous => 500,
        _ => throw new ArgumentOutOfRangeException(nameof(size), size, null),
    };

    private static PipelineCompactionStrategy CreateGentlePipeline(int tokenLimit, int messageLimit, IChatClient chatClient)
    {
        int messageTarget = messageLimit * 4 / 5;
        int tokenTarget = tokenLimit * 4 / 5;

        return new(
            new ToolResultCompactionStrategy(
                trigger: CompactionTriggers.MessagesExceed(messageLimit),
                target: CompactionTriggers.MessagesBelow(messageTarget)),
            new SummarizationCompactionStrategy(
                chatClient,
                trigger: CompactionTriggers.TokensExceed(tokenLimit),
                target: CompactionTriggers.TokensBelow(tokenTarget)));
    }

    private static PipelineCompactionStrategy CreateBalancedPipeline(int tokenLimit, int messageLimit, IChatClient chatClient)
    {
        int messageTarget = messageLimit * 3 / 4;
        int tokenTarget = tokenLimit * 4 / 5;

        return new(
            new ToolResultCompactionStrategy(
                trigger: CompactionTriggers.MessagesExceed(messageLimit),
                target: CompactionTriggers.MessagesBelow(messageTarget)),
            new SummarizationCompactionStrategy(
                chatClient,
                trigger: CompactionTriggers.TokensExceed(tokenLimit),
                target: CompactionTriggers.TokensBelow(tokenTarget)),
            new TruncationCompactionStrategy(
                trigger: CompactionTriggers.TokensExceed(tokenLimit),
                target: CompactionTriggers.TokensBelow(tokenTarget)));
    }

    private static PipelineCompactionStrategy CreateAggressivePipeline(int tokenLimit, int messageLimit, int turnLimit, IChatClient chatClient)
    {
        // Early stages trigger at half the limit so compaction kicks in sooner and
        // the sliding window and truncation backstop are reached less often.
        int messageTarget = messageLimit * 3 / 4;
        int tokenTarget = tokenLimit * 3 / 4;

        return new(
            new ToolResultCompactionStrategy(
                trigger: CompactionTriggers.MessagesExceed(messageLimit),
                target: CompactionTriggers.MessagesBelow(messageTarget)),
            new SummarizationCompactionStrategy(
                chatClient,
                trigger: CompactionTriggers.TokensExceed(tokenLimit),
                target: CompactionTriggers.TokensBelow(tokenTarget)),
            new SlidingWindowCompactionStrategy(
                trigger: CompactionTriggers.TokensExceed(tokenLimit),
                target: CompactionTriggers.TokensBelow(tokenTarget)),
            new TruncationCompactionStrategy(
                trigger: CompactionTriggers.TokensExceed(tokenLimit),
                target: CompactionTriggers.TokensBelow(tokenTarget)));
    }
}
