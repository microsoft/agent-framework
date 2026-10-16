// Copyright (c) Microsoft. All rights reserved.

using System.Runtime.CompilerServices;
using System.Threading;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI;

/// <summary>
/// AsyncLocal carrier that rolls up the token usage of sub-agents into the usage reported by the agent run that
/// invoked them.
/// </summary>
/// <remarks>
/// <para>
/// <see cref="ChatClientAgent"/> pushes a fresh <see cref="UsageAccumulator"/> onto this scope at the start of every
/// run, before its <see cref="AIContextProvider"/> instances are invoked. Because <see cref="AsyncLocal{T}"/>
/// mutations inside a child <c>async</c> method do not propagate back to the caller (copy-on-write semantics), the
/// accumulator is a reference type: code running within the run, such as the function produced by
/// <see cref="AIAgentExtensions.AsAIFunction"/>, captures <see cref="Current"/> and adds the sub-agent's reported
/// <see cref="AgentResponse.Usage"/> into it. When the run finishes, the agent merges the accumulated total into its
/// own <see cref="AgentResponse.Usage"/>.
/// </para>
/// <para>
/// Every sub-agent run establishes its own accumulator, so the usage it reports already includes its own sub-agents.
/// Only the call boundary reports usage to the parent, so in a chain A → B → C every agent's tokens are counted
/// exactly once.
/// </para>
/// <para>
/// The portion of a merged usage that came from sub-agents is tracked here, keyed by object identity, so that
/// <see cref="OpenTelemetryAgent"/> can keep reporting only the agent's own usage on its <c>invoke_agent</c> span.
/// </para>
/// </remarks>
internal static class SubAgentUsageScope
{
    private static readonly AsyncLocal<UsageAccumulator?> s_current = new();

    /// <summary>Maps a merged <see cref="UsageDetails"/> instance to the agent's own usage before the merge.</summary>
    private static readonly ConditionalWeakTable<UsageDetails, StrongBox<UsageDetails?>> s_ownUsageByMergedUsage = new();

    /// <summary>Tracks the <see cref="UsageContent"/> instances that carry only sub-agent usage on a streamed update.</summary>
    private static readonly ConditionalWeakTable<AIContent, object> s_subAgentUsageContents = new();

    /// <summary>
    /// Gets or sets the accumulator for the current agent run, or <see langword="null"/> when no run that rolls up
    /// sub-agent usage is in progress.
    /// </summary>
    public static UsageAccumulator? Current
    {
        get => s_current.Value;
        set => s_current.Value = value;
    }

    /// <summary>
    /// Creates a new <see cref="UsageDetails"/> that is the sum of <paramref name="ownUsage"/> and
    /// <paramref name="subAgentUsage"/>, remembering <paramref name="ownUsage"/> so that it can be recovered with
    /// <see cref="GetOwnUsage"/>.
    /// </summary>
    public static UsageDetails Merge(UsageDetails? ownUsage, UsageDetails subAgentUsage)
    {
        UsageDetails merged = new();
        if (ownUsage is not null)
        {
            merged.Add(ownUsage);
        }

        merged.Add(subAgentUsage);

        s_ownUsageByMergedUsage.Add(merged, new StrongBox<UsageDetails?>(ownUsage));
        return merged;
    }

    /// <summary>
    /// Returns the agent's own usage for a <see cref="UsageDetails"/> produced by <see cref="Merge"/>, or
    /// <paramref name="usage"/> itself when it was not produced by a merge.
    /// </summary>
    public static UsageDetails? GetOwnUsage(UsageDetails? usage) =>
        usage is not null && s_ownUsageByMergedUsage.TryGetValue(usage, out StrongBox<UsageDetails?>? own)
            ? own.Value
            : usage;

    /// <summary>
    /// Creates a <see cref="UsageContent"/> carrying sub-agent usage on a streamed update, marked so that it can be
    /// recognized with <see cref="IsSubAgentUsageContent"/>.
    /// </summary>
    public static UsageContent CreateSubAgentUsageContent(UsageDetails subAgentUsage)
    {
        UsageContent content = new(subAgentUsage);
        s_subAgentUsageContents.Add(content, content);
        return content;
    }

    /// <summary>
    /// Gets a value indicating whether <paramref name="content"/> was created by <see cref="CreateSubAgentUsageContent"/>.
    /// </summary>
    public static bool IsSubAgentUsageContent(AIContent content) =>
        s_subAgentUsageContents.TryGetValue(content, out _);

    /// <summary>
    /// A thread-safe running total of the usage reported by sub-agents during a single agent run.
    /// </summary>
    /// <remarks>
    /// Sub-agents may report concurrently, for example when the function-invoking client runs tool calls in parallel.
    /// </remarks>
    internal sealed class UsageAccumulator
    {
        private readonly object _lock = new();
        private UsageDetails? _total;

        /// <summary>Adds <paramref name="usage"/> to the running total. A <see langword="null"/> value is ignored.</summary>
        public void Add(UsageDetails? usage)
        {
            if (usage is null)
            {
                return;
            }

            lock (this._lock)
            {
                (this._total ??= new()).Add(usage);
            }
        }

        /// <summary>
        /// Gets a snapshot of the running total, or <see langword="null"/> if no sub-agent has reported usage.
        /// </summary>
        public UsageDetails? GetTotal()
        {
            lock (this._lock)
            {
                if (this._total is null)
                {
                    return null;
                }

                UsageDetails snapshot = new();
                snapshot.Add(this._total);
                return snapshot;
            }
        }
    }
}
