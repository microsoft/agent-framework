// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;

namespace Microsoft.Agents.AI;

/// <summary>
/// Loads <see cref="AgentSkill"/> instances from <c>skill://index.json</c> entries of a single
/// distribution <see cref="EntryType"/> (e.g. <c>skill-md</c> or <c>archive</c>).
/// </summary>
/// <remarks>
/// Implementations receive all index entries of their type as a batch so that types whose
/// materialization spans the whole set (e.g. <c>archive</c>, which reconciles and prunes a shared
/// on-disk directory) can reason about every advertised entry at once. The batch may be empty: every
/// registered loader is invoked even when the server advertises no entries of its type, so that
/// type-wide lifecycle work (such as pruning leftover archive directories) still runs.
/// </remarks>
internal interface IMcpSkillEntryLoader
{
    /// <summary>
    /// Gets the index entry <c>type</c> this loader handles (matched case-insensitively).
    /// </summary>
    string EntryType { get; }

    /// <summary>
    /// Loads the skills for every supplied entry. Entries that are invalid or fail to load are
    /// skipped (and logged) rather than throwing; the returned list contains only the skills that
    /// loaded successfully.
    /// </summary>
    /// <param name="entries">The index entries of this loader's <see cref="EntryType"/>. May be empty.</param>
    /// <param name="context">Contextual information about the agent and session requesting skills.</param>
    /// <param name="cancellationToken">A token to cancel the operation.</param>
    Task<IList<AgentSkill>> LoadAsync(IReadOnlyList<McpSkillIndexEntry> entries, AgentSkillsSourceContext context, CancellationToken cancellationToken);
}
