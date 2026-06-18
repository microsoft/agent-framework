// Copyright (c) Microsoft. All rights reserved.

using System.Diagnostics.CodeAnalysis;
using System.Linq;
using Microsoft.Shared.DiagnosticIds;

namespace Microsoft.Agents.AI.Compaction;

/// <summary>
/// Factory to create <see cref="CompactionTrigger"/> predicates.
/// </summary>
/// <remarks>
/// <para>
/// A <see cref="CompactionTrigger"/> defines a condition based on <see cref="CompactionMessageIndex"/> metrics used
/// by a <see cref="CompactionStrategy"/> to determine when to trigger compaction and when the target
/// compaction threshold has been met.
/// </para>
/// <para>
/// Combine triggers with <see cref="All"/> or <see cref="Any"/> for compound conditions.
/// </para>
/// </remarks>
[Experimental(DiagnosticIds.Experiments.AgentsAIExperiments)]
public static class CompactionTriggers
{
    /// <summary>
    /// Always trigger, regardless of the message index state.
    /// </summary>
    public static readonly CompactionTrigger Always =
        _ => true;

    /// <summary>
    /// Never trigger, regardless of the message index state.
    /// </summary>
    public static readonly CompactionTrigger Never =
        _ => false;

    /// <summary>
    /// Creates a trigger that fires when the included token count is below the specified maximum.
    /// </summary>
    /// <param name="maxTokens">The token threshold.</param>
    /// <returns>A <see cref="CompactionTrigger"/> that evaluates included token count.</returns>
    public static CompactionTrigger TokensBelow(int maxTokens) =>
        index => index.IncludedTokenCount < maxTokens;

    /// <summary>
    /// Creates a trigger that fires when the included token count exceeds the specified maximum.
    /// </summary>
    /// <param name="maxTokens">The token threshold.</param>
    /// <returns>A <see cref="CompactionTrigger"/> that evaluates included token count.</returns>
    public static CompactionTrigger TokensExceed(int maxTokens) =>
        index => index.IncludedTokenCount > maxTokens;

    /// <summary>
    /// Creates a trigger that fires when the included message count exceeds the specified maximum.
    /// </summary>
    /// <param name="maxMessages">The message threshold.</param>
    /// <returns>A <see cref="CompactionTrigger"/> that evaluates included message count.</returns>
    public static CompactionTrigger MessagesExceed(int maxMessages) =>
        index => index.IncludedMessageCount > maxMessages;

    /// <summary>
    /// Creates a trigger that fires when the included user turn count exceeds the specified maximum.
    /// </summary>
    /// <param name="maxTurns">The turn threshold.</param>
    /// <returns>A <see cref="CompactionTrigger"/> that evaluates included turn count.</returns>
    /// <remarks>
    /// <para>
    /// A user turn starts with a <see cref="CompactionGroupKind.User"/> group and includes all subsequent
    /// non-user, non-system groups until the next user group or end of conversation.  Each group is assigned
    /// a <see cref="CompactionMessageGroup.TurnIndex"/> indicating which user turn it belongs to.
    /// System messages (<see cref="CompactionGroupKind.System"/>) are always assigned a <see langword="null"/>
    /// <see cref="CompactionMessageGroup.TurnIndex"/> since they never belong to a user turn.
    /// </para>
    /// <para>
    /// The turn count is the number of distinct values defined by <see cref="CompactionMessageGroup.TurnIndex"/>.
    /// </para>
    /// </remarks>
    public static CompactionTrigger TurnsExceed(int maxTurns) =>
        index => index.IncludedTurnCount > maxTurns;

    /// <summary>
    /// Creates a trigger that fires when the included group count exceeds the specified maximum.
    /// </summary>
    /// <param name="maxGroups">The group threshold.</param>
    /// <returns>A <see cref="CompactionTrigger"/> that evaluates included group count.</returns>
    public static CompactionTrigger GroupsExceed(int maxGroups) =>
        index => index.IncludedGroupCount > maxGroups;

    /// <summary>
    /// Creates a trigger that fires when the included message index contains at least one
    /// non-excluded <see cref="CompactionGroupKind.ToolCall"/> group.
    /// </summary>
    /// <returns>A <see cref="CompactionTrigger"/> that evaluates included tool call presence.</returns>
    public static CompactionTrigger HasToolCalls() =>
        index => index.Groups.Any(g => !g.IsExcluded && g.Kind == CompactionGroupKind.ToolCall);

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
