// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Hosting.Channels.IntegrationTests.Support;

namespace Microsoft.Agents.AI.Hosting.Channels.IntegrationTests;

/// <summary>
/// Covers <see cref="WorkflowRunner"/> checkpoint behavior (Python parity with
/// <c>test_invoke_writes_checkpoint_under_isolation_key</c> / <c>test_stream_writes_checkpoint_under_isolation_key</c>):
/// with a persistent <see cref="FileHostStateStore"/> a run commits a checkpoint under the per-isolation-key
/// location and surfaces the resume id; with the in-memory store the runner runs forward without checkpointing.
/// </summary>
public class WorkflowCheckpointTests
{
    private static ChannelRequest Request(string isolationKey, IReadOnlyDictionary<string, object?>? attributes = null) =>
        new("test", "message.create", "hi")
        {
            Session = new ChannelSession { IsolationKey = isolationKey },
            Attributes = attributes ?? new Dictionary<string, object?>(),
        };

    private static string PerKeyDir(string root, string isolationKey) =>
        Path.Combine(root, "checkpoints", Convert.ToHexString(System.Text.Encoding.UTF8.GetBytes(isolationKey)));

    [Fact]
    public async Task FileStore_RunCommitsCheckpointAndSurfacesIdAsync()
    {
        var root = Path.Combine(Path.GetTempPath(), "afhost-cp-" + Guid.NewGuid().ToString("N"));
        try
        {
            using var store = new FileHostStateStore(new HostStatePathOptions { Root = root });
            var runner = new WorkflowRunner(WorkflowFactory.Echo(), store);

            var result = await runner.RunAsync(Request("alice"), default);

            var wr = Assert.IsType<WorkflowRunResult>(result.ResultObject);
            Assert.Equal(WorkflowRunStatus.Completed, wr.Status);
            Assert.Contains("echo: hi", wr.Outputs.Select(o => o?.ToString()));

            // a real checkpoint file (not just the index) was committed under the per-isolation-key location
            Assert.Contains(Directory.EnumerateFiles(PerKeyDir(root, "alice")), f => Path.GetFileName(f) != "index.jsonl");
            // the resume id is surfaced for the next turn
            Assert.True(result.Session!.Attributes.ContainsKey(WorkflowRunner.CheckpointIdAttribute));
        }
        finally
        {
            if (Directory.Exists(root)) { Directory.Delete(root, recursive: true); }
        }
    }

    [Fact]
    public async Task FileStore_StreamCommitsCheckpointAsync()
    {
        var root = Path.Combine(Path.GetTempPath(), "afhost-cp-" + Guid.NewGuid().ToString("N"));
        try
        {
            using var store = new FileHostStateStore(new HostStatePathOptions { Root = root });
            var runner = new WorkflowRunner(WorkflowFactory.Echo(), store);

            // Act - drive the streaming path
            await foreach (var _ in runner.StreamAsync(Request("bob"), default))
            {
            }

            // Assert - the streamed run also committed a checkpoint under its isolation key
            Assert.Contains(Directory.EnumerateFiles(PerKeyDir(root, "bob")), f => Path.GetFileName(f) != "index.jsonl");
        }
        finally
        {
            if (Directory.Exists(root)) { Directory.Delete(root, recursive: true); }
        }
    }

    [Fact]
    public async Task FileStore_ResumesFromSurfacedCheckpointIdAsync()
    {
        var root = Path.Combine(Path.GetTempPath(), "afhost-cp-" + Guid.NewGuid().ToString("N"));
        try
        {
            string checkpointId;

            // First turn: run, commit a checkpoint, and capture the surfaced resume id. The store is disposed
            // before the second turn so the exclusive index.jsonl lock is released (avoids a self-conflict).
            using (var store = new FileHostStateStore(new HostStatePathOptions { Root = root }))
            {
                var runner = new WorkflowRunner(WorkflowFactory.Echo(), store);
                var first = await runner.RunAsync(Request("carol"), default);
                checkpointId = Assert.IsType<string>(first.Session!.Attributes[WorkflowRunner.CheckpointIdAttribute]);
            }

            Assert.False(string.IsNullOrEmpty(checkpointId));

            // Second turn: pass the captured id back on the request attributes; the runner resumes from it.
            using (var store = new FileHostStateStore(new HostStatePathOptions { Root = root }))
            {
                var runner = new WorkflowRunner(WorkflowFactory.Echo(), store);
                var attributes = new Dictionary<string, object?> { [WorkflowRunner.CheckpointIdAttribute] = checkpointId };
                var second = await runner.RunAsync(Request("carol", attributes), default);

                var wr = Assert.IsType<WorkflowRunResult>(second.ResultObject);
                Assert.Equal(WorkflowRunStatus.Completed, wr.Status);
            }
        }
        finally
        {
            if (Directory.Exists(root)) { Directory.Delete(root, recursive: true); }
        }
    }

    [Fact]
    public async Task InMemoryStore_RunsWithoutCheckpointingAsync()
    {
        // Arrange - the in-memory store yields no persistent location, so no checkpointing happens
        var runner = new WorkflowRunner(WorkflowFactory.Echo(), new InMemoryHostStateStore());

        // Act
        var result = await runner.RunAsync(Request("alice"), default);

        // Assert - completed with real output, but no surfaced checkpoint id
        var wr = Assert.IsType<WorkflowRunResult>(result.ResultObject);
        Assert.Equal(WorkflowRunStatus.Completed, wr.Status);
        Assert.Contains("echo: hi", wr.Outputs.Select(o => o?.ToString()));
        Assert.False(result.Session!.Attributes.ContainsKey(WorkflowRunner.CheckpointIdAttribute));
    }
}
