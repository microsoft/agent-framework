// Copyright (c) Microsoft. All rights reserved.

using System.Diagnostics.CodeAnalysis;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Shared.DiagnosticIds;

namespace Microsoft.Agents.AI.Workflows.Checkpointing;

/// <summary>
/// Receives a notification once a workflow has been successfully restored from a checkpoint.
/// </summary>
/// <remarks>
/// <para>
/// Implement this alongside <see cref="ICheckpointStore{TStoreObject}"/> on a store that defers work, such as
/// deleting superseded checkpoints, until a restore is known to have succeeded.
/// <see cref="ICheckpointStore{TStoreObject}.RetrieveCheckpointAsync"/> runs before the stored checkpoint has been
/// deserialized, before it has been checked against the workflow being resumed, and before its state has been
/// imported. A store that cleans up there discards recoverable state whenever one of those later steps fails.
/// </para>
/// <para>
/// This is a separate interface rather than a member on <see cref="ICheckpointStore{TStoreObject}"/> so that
/// implementing it stays optional: existing stores continue to compile unchanged and are simply never notified.
/// </para>
/// <para>
/// <see cref="OnRestorationCompletedAsync"/> is invoked after the restore has already completed, so the workflow is
/// live by the time it runs and failing it cannot undo the restore. Exceptions leaving it are therefore suppressed
/// by the runner. An implementation is responsible for reporting its own failures and for leaving the store usable
/// when its work does not finish. It runs after every executor's
/// <see cref="Executor.OnCheckpointRestoredAsync"/> has completed, which is the distinction between the two: the
/// executor hook participates in the restore and can still fail it, this one cannot.
/// </para>
/// </remarks>
[Experimental(DiagnosticIds.Experiments.AgentsAIExperiments)]
public interface ICheckpointRestorationObserver
{
    /// <summary>
    /// Called after a workflow has been successfully restored from <paramref name="checkpoint"/>.
    /// </summary>
    /// <param name="sessionId">The workflow session that owns the checkpoint. Never null or empty.</param>
    /// <param name="checkpoint">Identifies the checkpoint the workflow was restored from.</param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests.</param>
    /// <returns>A <see cref="ValueTask"/> representing the asynchronous operation.</returns>
    /// <remarks>
    /// The restore has already succeeded when this runs. Exceptions thrown here are suppressed rather than surfaced
    /// to the caller that resumed the workflow, so an implementation that needs its failures to be visible has to
    /// report them itself.
    /// </remarks>
    ValueTask OnRestorationCompletedAsync(string sessionId, CheckpointInfo checkpoint, CancellationToken cancellationToken = default);
}
