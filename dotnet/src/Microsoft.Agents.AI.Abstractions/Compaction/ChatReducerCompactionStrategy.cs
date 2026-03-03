// Copyright (c) Microsoft. All rights reserved.

using System;
using Microsoft.Extensions.AI;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI.Compaction;

/// <summary>
/// Represents a chat history compaction strategy that uses a condition function to determine when compaction should
/// occur.
/// </summary>
/// <remarks>
/// This strategy evaluates a user-provided condition against compaction metrics to decide whether to
/// compact the chat history. It is useful for scenarios where compaction should be triggered based on custom thresholds
/// or criteria. Inherits from ChatHistoryCompactionStrategy.
/// </remarks>
public class ChatReducerCompactionStrategy : ChatHistoryCompactionStrategy
{
    private readonly Func<ChatHistoryMetric, bool> _condition;

    /// <summary>
    /// Initializes a new instance of the <see cref="ChatReducerCompactionStrategy"/> class.
    /// </summary>
    public ChatReducerCompactionStrategy(
        IChatReducer reducer,
        Func<ChatHistoryMetric, bool> condition)
        : base(reducer)
    {
        this._condition = Throw.IfNull(condition);
    }

    /// <inheritdoc/>
    protected override bool ShouldCompact(ChatHistoryMetric metrics) => this._condition(metrics);
}
