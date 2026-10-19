// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.IO;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Workflows.Checkpointing;

namespace Microsoft.Agents.AI.Workflows.UnitTests;

/// <summary>
/// Verifies that a checkpoint store implementing <see cref="ICheckpointRestorationObserver"/> is told about a
/// restore only once that restore has actually succeeded. A store that cleans up when a checkpoint is merely read
/// discards state the caller could still have recovered from, because reading happens before the checkpoint is
/// deserialized, before it is matched against the workflow, and before its state is imported.
/// </summary>
public class CheckpointRestorationObserverTests
{
    private const string EchoId = "Echo";

    /// <summary>
    /// The executor that starts these workflows. <paramref name="failOnRestore"/> makes it refuse a restore after the
    /// checkpoint has been read and matched against the workflow, which is the only way to fail a restore from
    /// inside the import. It is a constructor argument rather than a separate type because a different type would
    /// change the workflow identity and fail the compatibility check first.
    /// </summary>
    private sealed class EchoExecutor(bool failOnRestore = false, string id = EchoId) : Executor<string, string>(id)
    {
        public override ValueTask<string> HandleAsync(string message, IWorkflowContext context, CancellationToken cancellationToken = default)
            => new(message);

        protected internal override ValueTask OnCheckpointRestoredAsync(IWorkflowContext context, CancellationToken cancellationToken = default)
            => failOnRestore
                ? throw new InvalidOperationException("executor refused to restore")
                : default;
    }

    /// <summary>Adds a superstep between the start and the end, so the run commits more than one checkpoint.</summary>
    private sealed class RelayExecutor(string id) : Executor<string, string>(id)
    {
        public override ValueTask<string> HandleAsync(string message, IWorkflowContext context, CancellationToken cancellationToken = default)
            => new(message);
    }

    /// <summary>Ends the graph, so the run halts instead of waiting on anything.</summary>
    private sealed class SinkExecutor(string id) : Executor<string>(id)
    {
        public override ValueTask HandleAsync(string message, IWorkflowContext context, CancellationToken cancellationToken = default)
            => context.YieldOutputAsync(message, cancellationToken);
    }

    [Fact]
    public async Task Restore_Succeeds_NotifiesTheStoreAsync()
    {
        // Arrange
        ObservingJsonStore store = new();
        (Workflow workflow, CheckpointInfo checkpoint, CheckpointManager manager) = await RunAndCheckpointAsync(store);

        // Act
        await ResumeAsync(workflow, checkpoint, manager);

        // Assert
        Assert.Equal([checkpoint], store.RestorationsObserved);
    }

    [Fact]
    public async Task Restore_IncompatibleWorkflow_DoesNotNotifyTheStoreAsync()
    {
        // Arrange: resume a workflow the checkpoint was not taken from.
        ObservingJsonStore store = new();
        (_, CheckpointInfo checkpoint, CheckpointManager manager) = await RunAndCheckpointAsync(store);
        Workflow otherWorkflow = BuildWorkflow(new EchoExecutor(id: "OtherEcho"));

        // Act
        async Task resumeAsync() => await ResumeAsync(otherWorkflow, checkpoint, manager);

        // Assert: the mismatch is caught after the checkpoint was read, so nothing may have been cleaned up.
        await Assert.ThrowsAsync<InvalidDataException>(resumeAsync);
        Assert.Empty(store.RestorationsObserved);
    }

    [Fact]
    public async Task Restore_MalformedCheckpointData_DoesNotNotifyTheStoreAsync()
    {
        // Arrange: the stored JSON comes back as something that is not a checkpoint at all.
        ObservingJsonStore store = new();
        (Workflow workflow, CheckpointInfo checkpoint, CheckpointManager manager) = await RunAndCheckpointAsync(store);
        store.MutateOnRetrieve = _ => JsonDocument.Parse("[]").RootElement.Clone();

        // Act
        async Task resumeAsync() => await ResumeAsync(workflow, checkpoint, manager);

        // Assert: deserializing the checkpoint fails, which happens after the store has already been read.
        await Assert.ThrowsAsync<JsonException>(resumeAsync);
        Assert.Empty(store.RestorationsObserved);
    }

    [Fact]
    public async Task Restore_StateImportFails_DoesNotNotifyTheStoreAsync()
    {
        // Arrange: the checkpoint reads back and matches the workflow, but its runner state names an executor the
        // workflow does not contain, so importing that state throws. The workflow section is left untouched, so the
        // failure happens in RunContext.ImportStateAsync rather than in the compatibility check before it.
        ObservingJsonStore store = new();
        (Workflow workflow, CheckpointInfo checkpoint, CheckpointManager manager) = await RunAndCheckpointAsync(store);
        // The two-argument Replace is already ordinal, and is the overload available on every target framework.
        const string ExecutorList = "\"instantiatedExecutors\":[";
        bool mutationApplied = false;
        store.MutateOnRetrieve = value =>
        {
            string json = value.GetRawText();
            mutationApplied = json.Contains(ExecutorList);

            return JsonDocument.Parse(json.Replace(ExecutorList, ExecutorList + "\"Ghost\",")).RootElement.Clone();
        };

        // Act
        async Task resumeAsync() => await ResumeAsync(workflow, checkpoint, manager);

        // Assert: the import itself is what fails, not the compatibility check that runs before it.
        InvalidOperationException importFailure = await Assert.ThrowsAsync<InvalidOperationException>(resumeAsync);
        Assert.Equal("Executor with ID 'Ghost' is not registered.", importFailure.Message);
        Assert.Empty(store.RestorationsObserved);

        // Reported rather than inferred, so that a checkpoint whose shape no longer carries this property fails
        // here instead of quietly leaving the test asserting nothing.
        Assert.True(mutationApplied, "the checkpoint must still serialize the runner's instantiated executors");
    }

    [Fact]
    public async Task Restore_ExecutorRestoreHookFails_DoesNotNotifyTheStoreAsync()
    {
        // Arrange: the checkpoint reads back fine and matches the workflow, but an executor refuses the restore.
        ObservingJsonStore store = new();
        (_, CheckpointInfo checkpoint, CheckpointManager manager) = await RunAndCheckpointAsync(store);
        Workflow failingWorkflow = BuildWorkflow(new EchoExecutor(failOnRestore: true));

        // Act
        async Task resumeAsync() => await ResumeAsync(failingWorkflow, checkpoint, manager);

        // Assert
        InvalidOperationException restoreFailure = await Assert.ThrowsAsync<InvalidOperationException>(resumeAsync);
        Assert.Equal("executor refused to restore", restoreFailure.Message);
        Assert.Empty(store.RestorationsObserved);
    }

    [Fact]
    public async Task Restore_StoreThrowsWhenNotified_StillSucceedsAsync()
    {
        // Arrange: housekeeping runs after the workflow is already live, so failing it cannot undo the restore.
        ObservingJsonStore store = new() { ObserverFailure = new InvalidOperationException("cleanup refused") };
        (Workflow workflow, CheckpointInfo checkpoint, CheckpointManager manager) = await RunAndCheckpointAsync(store);

        // Act
        async Task resumeAsync() => await ResumeAsync(workflow, checkpoint, manager);

        // Assert
        Assert.Null(await Record.ExceptionAsync(resumeAsync));
        Assert.Equal([checkpoint], store.RestorationsObserved);
    }

    [Fact]
    public async Task Restore_StorePrunesWhenNotified_LeavesOnlyExistingCheckpointsListedAsync()
    {
        // Arrange: a store that really does delete the superseded checkpoints once the restore has succeeded, which
        // is the whole point of deferring the cleanup to that moment.
        ObservingJsonStore store = new() { PruneAncestryOnRestore = true };
        (Workflow workflow, CheckpointInfo checkpoint, CheckpointManager manager) = await RunAndCheckpointAsync(store);

        // Act
        IReadOnlyList<CheckpointInfo> reported = await ResumeAsync(workflow, checkpoint, manager);

        // Assert: the run must not go on offering checkpoints the store has just deleted.
        Assert.Equal([checkpoint], reported);
    }

    [Fact]
    public async Task Restore_StorePrunesThenThrows_StillLeavesOnlyExistingCheckpointsListedAsync()
    {
        // Arrange: a store that deletes and then fails has still changed what it holds, so the run cannot assume
        // the checkpoint list it read before the notification is still accurate.
        ObservingJsonStore store = new()
        {
            PruneAncestryOnRestore = true,
            ObserverFailure = new InvalidOperationException("cleanup refused"),
        };
        (Workflow workflow, CheckpointInfo checkpoint, CheckpointManager manager) = await RunAndCheckpointAsync(store);

        // Act
        IReadOnlyList<CheckpointInfo> reported = await ResumeAsync(workflow, checkpoint, manager);

        // Assert
        Assert.Equal([checkpoint], reported);
    }

    [Fact]
    public async Task Restore_IndexEnumerationFailsAfterRestore_KeepsTheCheckpointsAlreadyListedAsync()
    {
        // Arrange: RetrieveIndexAsync hands back an IEnumerable a store may enumerate lazily, so the post-restore
        // re-read can fail partway rather than when it is awaited. The restore has already succeeded by then, so the
        // run must keep the checkpoints it had rather than be left with an empty or half-rebuilt list.
        ObservingJsonStore store = new() { FailIndexEnumerationAfterRestore = true };
        (Workflow workflow, CheckpointInfo checkpoint, CheckpointManager manager) = await RunAndCheckpointAsync(store);

        // Act
        IReadOnlyList<CheckpointInfo> reported = await ResumeAsync(workflow, checkpoint, manager);

        // Assert: the resume survives, and Checkpoints still lists everything the store holds.
        Assert.Contains(checkpoint, reported);
        Assert.True(reported.Count > 1, "a failed re-read must not shrink the list the run already had");
    }

    [Fact]
    public async Task Restore_StoreDoesNotObserveRestorations_StillSucceedsAsync()
    {
        // Arrange: implementing the interface is optional, so a store that does not is simply never notified.
        InMemoryJsonStore store = new();
        CheckpointManager manager = CheckpointManager.CreateJson(store);
        (Workflow workflow, CheckpointInfo checkpoint) = await RunAndCheckpointAsync(manager);

        // Act
        async Task resumeAsync() => await ResumeAsync(workflow, checkpoint, manager);

        // Assert
        Assert.Null(await Record.ExceptionAsync(resumeAsync));
    }

    /// <summary>
    /// Builds the workflow the tests checkpoint and resume. The echo executor starts the run, so it is instantiated
    /// and therefore takes part in the restore, which is what lets a test fail the restore from inside an executor.
    /// The chain is three executors long so the run takes several supersteps and therefore commits several
    /// checkpoints, which is what gives a pruning store an ancestry to delete.
    /// </summary>
    private static Workflow BuildWorkflow(EchoExecutor echo)
    {
        RelayExecutor relay = new("Relay");
        SinkExecutor sink = new("Sink");

        return new WorkflowBuilder(echo).AddEdge(echo, relay)
                                        .AddEdge(relay, sink)
                                        .WithOutputFrom(sink)
                                        .Build();
    }

    private static async Task<(Workflow Workflow, CheckpointInfo Checkpoint, CheckpointManager Manager)> RunAndCheckpointAsync(JsonCheckpointStore store)
    {
        CheckpointManager manager = CheckpointManager.CreateJson(store);
        (Workflow workflow, CheckpointInfo checkpoint) = await RunAndCheckpointAsync(manager);
        return (workflow, checkpoint, manager);
    }

    private static async Task<(Workflow Workflow, CheckpointInfo Checkpoint)> RunAndCheckpointAsync(CheckpointManager manager)
    {
        Workflow workflow = BuildWorkflow(new EchoExecutor());
        await using Run run = await InProcessExecution.Default.WithCheckpointing(manager).RunAsync(workflow, "Hello", Guid.NewGuid().ToString());

        // More than one, so that a store pruning the ancestry has something to remove. Without that the tests
        // asserting the checkpoint index is re-read after pruning would pass whether or not the re-read happens.
        Assert.True(run.Checkpoints.Count > 1, "the resume needs a checkpoint to restore and an ancestor to prune");
        return (workflow, run.Checkpoints[run.Checkpoints.Count - 1]);
    }

    /// <summary>Resumes from the checkpoint and returns the checkpoints the resumed run reports afterwards.</summary>
    private static async Task<IReadOnlyList<CheckpointInfo>> ResumeAsync(Workflow workflow, CheckpointInfo checkpoint, CheckpointManager manager)
    {
        await using Run resumed = await InProcessExecution.Default.WithCheckpointing(manager).ResumeAsync(workflow, checkpoint);

        return [.. resumed.Checkpoints];
    }

    /// <summary>
    /// A store that records the restores it is told about, and can corrupt what it hands back, delete the resumed
    /// checkpoint's ancestry the way a real store defers doing, or fail when notified.
    /// </summary>
    private sealed class ObservingJsonStore : JsonCheckpointStore, ICheckpointRestorationObserver
    {
        private readonly List<CheckpointInfo> _index = [];
        private readonly Dictionary<CheckpointInfo, JsonElement> _checkpoints = [];

        public List<CheckpointInfo> RestorationsObserved { get; } = [];

        /// <summary>Rewrites what a read returns, to model checkpoint data the marshaller cannot make sense of.</summary>
        public Func<JsonElement, JsonElement>? MutateOnRetrieve { get; set; }

        /// <summary>Thrown when the store is told a restore completed, to model failing housekeeping.</summary>
        public Exception? ObserverFailure { get; init; }

        /// <summary>
        /// Deletes everything but the resumed checkpoint when the store is told a restore completed, modelling the
        /// housekeeping a real store defers until then. Runs before <see cref="ObserverFailure"/> is thrown, so the
        /// store can prune and still fail.
        /// </summary>
        public bool PruneAncestryOnRestore { get; init; }

        /// <summary>Makes the post-restore index read fail while it is being enumerated, not when it is awaited.</summary>
        public bool FailIndexEnumerationAfterRestore { get; init; }

        public override ValueTask<CheckpointInfo> CreateCheckpointAsync(string sessionId, JsonElement value, CheckpointInfo? parent = null)
        {
            CheckpointInfo key = new(sessionId);
            this._checkpoints[key] = value;
            this._index.Add(key);

            return new(key);
        }

        public override ValueTask<JsonElement> RetrieveCheckpointAsync(string sessionId, CheckpointInfo key)
        {
            if (!this._checkpoints.TryGetValue(key, out JsonElement value))
            {
                throw new KeyNotFoundException($"Could not retrieve checkpoint with id {key.CheckpointId} for session {sessionId}");
            }

            return new(this.MutateOnRetrieve is null ? value : this.MutateOnRetrieve(value));
        }

        public override ValueTask<IEnumerable<CheckpointInfo>> RetrieveIndexAsync(string sessionId, CheckpointInfo? withParent = null)
            => new(this.FailIndexEnumerationAfterRestore && this.RestorationsObserved.Count > 0
                    ? ThrowPartWayThrough(this._index)
                    : this._index.ToArray());

        /// <summary>
        /// Yields the first entry and then throws, modelling a store whose index is enumerated lazily and fails
        /// partway. The runner must not have emptied its own list before finding that out.
        /// </summary>
        private static IEnumerable<CheckpointInfo> ThrowPartWayThrough(List<CheckpointInfo> index)
        {
            foreach (CheckpointInfo entry in index)
            {
                yield return entry;

                throw new InvalidOperationException("index enumeration failed partway");
            }
        }

        public ValueTask OnRestorationCompletedAsync(string sessionId, CheckpointInfo checkpoint, CancellationToken cancellationToken = default)
        {
            this.RestorationsObserved.Add(checkpoint);

            if (this.PruneAncestryOnRestore)
            {
                foreach (CheckpointInfo superseded in this._index.ToArray())
                {
                    if (superseded != checkpoint)
                    {
                        this._index.Remove(superseded);
                        this._checkpoints.Remove(superseded);
                    }
                }
            }

            if (this.ObserverFailure is not null)
            {
                throw this.ObserverFailure;
            }

            return default;
        }
    }
}
