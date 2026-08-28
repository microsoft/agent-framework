// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.IO;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using FluentAssertions;
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
        store.RestorationsObserved.Should().Equal([checkpoint]);
    }

    [Fact]
    public async Task Restore_IncompatibleWorkflow_DoesNotNotifyTheStoreAsync()
    {
        // Arrange: resume a workflow the checkpoint was not taken from.
        ObservingJsonStore store = new();
        (_, CheckpointInfo checkpoint, CheckpointManager manager) = await RunAndCheckpointAsync(store);
        Workflow otherWorkflow = BuildWorkflow(new EchoExecutor(id: "OtherEcho"));

        // Act
        Func<Task> resume = () => ResumeAsync(otherWorkflow, checkpoint, manager);

        // Assert: the mismatch is caught after the checkpoint was read, so nothing may have been cleaned up.
        await resume.Should().ThrowAsync<InvalidDataException>();
        store.RestorationsObserved.Should().BeEmpty();
    }

    [Fact]
    public async Task Restore_MalformedCheckpointData_DoesNotNotifyTheStoreAsync()
    {
        // Arrange: the stored JSON comes back as something that is not a checkpoint at all.
        ObservingJsonStore store = new();
        (Workflow workflow, CheckpointInfo checkpoint, CheckpointManager manager) = await RunAndCheckpointAsync(store);
        store.MutateOnRetrieve = _ => JsonDocument.Parse("[]").RootElement.Clone();

        // Act
        Func<Task> resume = () => ResumeAsync(workflow, checkpoint, manager);

        // Assert: deserializing the checkpoint fails, which happens after the store has already been read.
        await resume.Should().ThrowAsync<JsonException>();
        store.RestorationsObserved.Should().BeEmpty();
    }

    [Fact]
    public async Task Restore_ExecutorRestoreHookFails_DoesNotNotifyTheStoreAsync()
    {
        // Arrange: the checkpoint reads back fine and matches the workflow, but an executor refuses the restore.
        ObservingJsonStore store = new();
        (_, CheckpointInfo checkpoint, CheckpointManager manager) = await RunAndCheckpointAsync(store);
        Workflow failingWorkflow = BuildWorkflow(new EchoExecutor(failOnRestore: true));

        // Act
        Func<Task> resume = () => ResumeAsync(failingWorkflow, checkpoint, manager);

        // Assert
        await resume.Should().ThrowAsync<InvalidOperationException>().WithMessage("executor refused to restore");
        store.RestorationsObserved.Should().BeEmpty();
    }

    [Fact]
    public async Task Restore_StoreThrowsWhenNotified_StillSucceedsAsync()
    {
        // Arrange: housekeeping runs after the workflow is already live, so failing it cannot undo the restore.
        ObservingJsonStore store = new() { ObserverFailure = new InvalidOperationException("cleanup refused") };
        (Workflow workflow, CheckpointInfo checkpoint, CheckpointManager manager) = await RunAndCheckpointAsync(store);

        // Act
        Func<Task> resume = () => ResumeAsync(workflow, checkpoint, manager);

        // Assert
        await resume.Should().NotThrowAsync();
        store.RestorationsObserved.Should().Equal([checkpoint]);
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
        reported.Should().Equal([checkpoint]);
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
        reported.Should().Equal([checkpoint]);
    }

    [Fact]
    public async Task Restore_StoreDoesNotObserveRestorations_StillSucceedsAsync()
    {
        // Arrange: implementing the interface is optional, so a store that does not is simply never notified.
        InMemoryJsonStore store = new();
        CheckpointManager manager = CheckpointManager.CreateJson(store);
        (Workflow workflow, CheckpointInfo checkpoint) = await RunAndCheckpointAsync(manager);

        // Act
        Func<Task> resume = () => ResumeAsync(workflow, checkpoint, manager);

        // Assert
        await resume.Should().NotThrowAsync();
    }

    /// <summary>
    /// Builds the workflow the tests checkpoint and resume. The echo executor starts the run, so it is instantiated
    /// and therefore takes part in the restore, which is what lets a test fail the restore from inside an executor.
    /// </summary>
    /// <summary>
    /// Builds the workflow the tests checkpoint and resume. The chain is three executors long so the run takes
    /// several supersteps and therefore commits several checkpoints, which is what gives a pruning store an
    /// ancestry to delete.
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
        run.Checkpoints.Count.Should().BeGreaterThan(1, "the resume needs a checkpoint to restore and an ancestor to prune");
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
            => new(this._index.ToArray());

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
