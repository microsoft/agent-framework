// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json;
using System.Text.RegularExpressions;
using System.Threading;
using System.Threading.Tasks;
using FluentAssertions;
using Microsoft.Agents.AI.Workflows.Checkpointing;
using Microsoft.Agents.AI.Workflows.InProc;

namespace Microsoft.Agents.AI.Workflows.UnitTests;

/// <summary>
/// Verifies that a checkpoint serialized through <see cref="JsonCheckpointStore"/> can be restored
/// after every <c>Version=X.Y.Z.W</c> substring in the persisted JSON is rewritten to a different value.
/// </summary>
public class CheckpointVersionToleranceTests
{
    private sealed class EchoExecutor() : Executor("Echo")
    {
        protected override ProtocolBuilder ConfigureProtocol(ProtocolBuilder protocolBuilder)
            => protocolBuilder.ConfigureRoutes(routeBuilder =>
                                               routeBuilder.AddHandler<string>((msg, ctx) => ctx.SendMessageAsync(msg)));
    }

    [Theory]
    [InlineData(ExecutionEnvironment.InProcess_OffThread)]
    [InlineData(ExecutionEnvironment.InProcess_Lockstep)]
    internal async Task Test_Checkpoint_Resumes_AfterAssemblyVersionRewriteAsync(ExecutionEnvironment environment)
    {
        // Arrange
        RequestPort<string, string> requestPort = RequestPort.Create<string, string>("TestPort");
        EchoExecutor echo = new();

        Workflow workflow = new WorkflowBuilder(requestPort)
            .AddEdge(requestPort, echo)
            .Build();

        VersionMutatingJsonStore store = new();
        CheckpointManager checkpointManager = CheckpointManager.CreateJson(store);
        InProcessExecutionEnvironment env = environment.ToWorkflowExecutionEnvironment();

        // Run the workflow and capture a checkpoint.
        CheckpointInfo? checkpoint = null;
        await using (StreamingRun firstRun = await env.WithCheckpointing(checkpointManager)
                                                      .RunStreamingAsync(workflow, "Hello"))
        {
            await foreach (WorkflowEvent evt in firstRun.WatchStreamAsync(blockOnPendingRequest: false))
            {
                if (evt is SuperStepCompletedEvent step && step.CompletionInfo?.Checkpoint is { } cp)
                {
                    checkpoint = cp;
                }
            }
        }

        checkpoint.Should().NotBeNull();
        store.MutationApplied.Should().BeFalse();

        // Resume against the mutated store, which rewrites every Version=X.Y.Z.W in the persisted JSON.
        Func<Task> resume = async () =>
        {
            await using StreamingRun resumed = await env.WithCheckpointing(checkpointManager)
                                                        .ResumeStreamingAsync(workflow, checkpoint!);
            using CancellationTokenSource cts = new(TimeSpan.FromSeconds(10));
            await foreach (WorkflowEvent _ in resumed.WatchStreamAsync(blockOnPendingRequest: false, cts.Token))
            {
            }
        };

        await resume.Should().NotThrowAsync("resume must succeed when persisted assembly versions differ from loaded ones");
        store.MutationApplied.Should().BeTrue();
    }

    /// <summary>
    /// JSON checkpoint store that rewrites every <c>Version=N.N.N.N</c> token in the persisted
    /// payload at retrieval time.
    /// </summary>
    private sealed class VersionMutatingJsonStore : JsonCheckpointStore
    {
        private static readonly Regex s_versionPattern = new(@"Version=\d+\.\d+\.\d+\.\d+", RegexOptions.Compiled);

        private readonly Dictionary<string, Dictionary<string, JsonElement>> _store = [];

        public string ReplacementVersion { get; init; } = "99.0.0.0";

        public bool MutationApplied { get; private set; }

        public override ValueTask<CheckpointInfo> CreateCheckpointAsync(string sessionId, JsonElement value, CheckpointInfo? parent = null)
        {
            if (!this._store.TryGetValue(sessionId, out Dictionary<string, JsonElement>? sessionStore))
            {
                sessionStore = this._store[sessionId] = [];
            }

            CheckpointInfo info = new(sessionId);
            sessionStore[info.CheckpointId] = value.Clone();
            return new ValueTask<CheckpointInfo>(info);
        }

        public override ValueTask<JsonElement> RetrieveCheckpointAsync(string sessionId, CheckpointInfo key)
        {
            if (!this._store.TryGetValue(sessionId, out Dictionary<string, JsonElement>? sessionStore)
                || !sessionStore.TryGetValue(key.CheckpointId, out JsonElement raw))
            {
                throw new KeyNotFoundException($"Could not retrieve checkpoint with id {key.CheckpointId} for session {sessionId}");
            }

            string rawText = raw.GetRawText();
            string mutatedText = s_versionPattern.Replace(rawText, $"Version={this.ReplacementVersion}");

            if (!ReferenceEquals(rawText, mutatedText) && rawText != mutatedText)
            {
                this.MutationApplied = true;
            }

            using JsonDocument doc = JsonDocument.Parse(mutatedText);
            return new ValueTask<JsonElement>(doc.RootElement.Clone());
        }

        public override ValueTask<IEnumerable<CheckpointInfo>> RetrieveIndexAsync(string sessionId, CheckpointInfo? withParent = null)
        {
            if (!this._store.TryGetValue(sessionId, out Dictionary<string, JsonElement>? sessionStore))
            {
                return new ValueTask<IEnumerable<CheckpointInfo>>(Array.Empty<CheckpointInfo>());
            }

            IEnumerable<CheckpointInfo> infos = sessionStore.Keys.Select(id => new CheckpointInfo(sessionId, id));
            return new ValueTask<IEnumerable<CheckpointInfo>>(infos);
        }
    }
}
