// Copyright (c) Microsoft. All rights reserved.

using System.Diagnostics.CodeAnalysis;
using System.Linq;
using Microsoft.Shared.DiagnosticIds;

namespace Microsoft.Agents.AI.Compaction;

/// <summary>
/// Provides factory methods for common <see cref="CompactionTrigger"/> predicates.
/// </summary>
/// <remarks>
/// These triggers evaluate included (non-excluded) metrics from the <see cref="MessageIndex"/>.
/// Combine triggers with <see cref="All"/> or <see cref="Any"/> for compound conditions,
/// or write a custom lambda for full flexibility.
/// </remarks>
[Experimental(DiagnosticIds.Experiments.AgentsAIExperiments)]
public static class CompactionTriggers
{
    /// <summary>
    /// Always trigger compaction, regardless of the message index state.
    /// </summary>
    public static readonly CompactionTrigger Always =
        _ => true;

    /// <summary>
    /// Always trigger compaction, regardless of the message index state.
    /// </summary>
    public static readonly CompactionTrigger Never =
        _ => false;

    /// <summary>
    /// Creates a trigger that fires when the included token count is below the specified maximum.
    /// </summary>
    /// <param name="maxTokens">The token threshold. Compaction proceeds when included tokens exceed this value.</param>
    /// <returns>A <see cref="CompactionTrigger"/> that evaluates included token count.</returns>
    public static CompactionTrigger TokensBelow(int maxTokens) =>
        index => index.IncludedTokenCount < maxTokens;

    /// <summary>
    /// Creates a trigger that fires when the included token count exceeds the specified maximum.
    /// </summary>
    /// <param name="maxTokens">The token threshold. Compaction proceeds when included tokens exceed this value.</param>
    /// <returns>A <see cref="CompactionTrigger"/> that evaluates included token count.</returns>
    public static CompactionTrigger TokensExceed(int maxTokens) =>
        index => index.IncludedTokenCount > maxTokens;

    /// <summary>
    /// Creates a trigger that fires when the included message count exceeds the specified maximum.
    /// </summary>
    /// <param name="maxMessages">The message threshold. Compaction proceeds when included messages exceed this value.</param>
    /// <returns>A <see cref="CompactionTrigger"/> that evaluates included message count.</returns>
    public static CompactionTrigger MessagesExceed(int maxMessages) =>
        index => index.IncludedMessageCount > maxMessages;

    /// <summary>
    /// Creates a trigger that fires when the included user turn count exceeds the specified maximum.
    /// </summary>
    /// <param name="maxTurns">The turn threshold. Compaction proceeds when included turns exceed this value.</param>
    /// <returns>A <see cref="CompactionTrigger"/> that evaluates included turn count.</returns>
    public static CompactionTrigger TurnsExceed(int maxTurns) =>
        index => index.IncludedTurnCount > maxTurns;

    /// <summary>
    /// Creates a trigger that fires when the included group count exceeds the specified maximum.
    /// </summary>
    /// <param name="maxGroups">The group threshold. Compaction proceeds when included groups exceed this value.</param>
    /// <returns>A <see cref="CompactionTrigger"/> that evaluates included group count.</returns>
    public static CompactionTrigger GroupsExceed(int maxGroups) =>
        index => index.IncludedGroupCount > maxGroups;

    /// <summary>
    /// Creates a trigger that fires when the included message index contains at least one
    /// non-excluded <see cref="MessageGroupKind.ToolCall"/> group.
    /// </summary>
    /// <returns>A <see cref="CompactionTrigger"/> that evaluates included tool call presence.</returns>
    public static CompactionTrigger HasToolCalls() =>
        index => index.Groups.Any(g => !g.IsExcluded && g.Kind == MessageGroupKind.ToolCall);

    /// <summary>
    /// Creates a compound trigger that fires only when <b>all</b> of the specified triggers fire.
    /// </summary>
    /// <param name="triggers">The triggers to combine with logical AND.</param>
    /// <returns>A <see cref="CompactionTrigger"/> that requires all conditions to be met.</returns>
    public static CompactionTrigger All(params CompactionTrigger[] triggers) =>
        index =>
        {
            for (int i = 0; i < triggers.Length; i++)
            {
                if (!triggers[i](index))
                {
                    return false;
                }
            }

            return true;
        };

    /// <summary>
    /// Creates a compound trigger that fires when <b>any</b> of the specified triggers fire.
    /// </summary>
    /// <param name="triggers">The triggers to combine with logical OR.</param>
    /// <returns>A <see cref="CompactionTrigger"/> that requires at least one condition to be met.</returns>
    public static CompactionTrigger Any(params CompactionTrigger[] triggers) =>
        index =>
        {
            for (int i = 0; i < triggers.Length; i++)
            {
                if (triggers[i](index))
                {
                    return true;
                }
            }

            return false;
        };
}
