// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Workflows.UnitTests.Futures;

/// <summary>
/// Runner-level coverage for <see cref="Workflows.Futures.EnableAgentResponseOutputTaggingAndFiltering"/>.
/// Exercises every combination of (flag on/off) × (designation kind) × (payload shape) to pin the
/// runner's behavior in both the legacy bypass path and the unified filter-and-tag path.
/// </summary>
public static partial class FuturesTests
{
    [Collection(FuturesSerialCollection.Name)]
    public class AgentResponseOutputFilteringAndTaggingTests
    {
        private const string SourceId = "yielder";

        private static AgentResponse SampleResponse(string text = "hi")
            => new(new ChatMessage(ChatRole.Assistant, text));

        private static AgentResponseUpdate SampleUpdate(string text = "tick")
            => new(ChatRole.Assistant, text);

        private static async Task<List<WorkflowEvent>> RunAsync<T>(Workflow workflow, T input) where T : notnull
        {
            List<WorkflowEvent> events = [];
            await using StreamingRun run = await InProcessExecution.RunStreamingAsync(workflow, input).ConfigureAwait(false);
            await foreach (WorkflowEvent evt in run.WatchStreamAsync().ConfigureAwait(false))
            {
                events.Add(evt);
            }
            return events;
        }

        private static Workflow BuildAgentResponseWorkflow(Action<WorkflowBuilder, YieldAgentResponseExecutor>? designate = null)
        {
            YieldAgentResponseExecutor exec = new(SourceId);
            WorkflowBuilder builder = new(exec);
            designate?.Invoke(builder, exec);
            return builder.Build();
        }

        private static Workflow BuildAgentResponseUpdateWorkflow(Action<WorkflowBuilder, YieldAgentResponseUpdateExecutor>? designate = null)
        {
            YieldAgentResponseUpdateExecutor exec = new(SourceId);
            WorkflowBuilder builder = new(exec);
            designate?.Invoke(builder, exec);
            return builder.Build();
        }

        private static Workflow BuildPocoWorkflow(Action<WorkflowBuilder, YieldPocoExecutor>? designate = null)
        {
            YieldPocoExecutor exec = new(SourceId);
            WorkflowBuilder builder = new(exec);
            designate?.Invoke(builder, exec);
            return builder.Build();
        }

        // F1
        [Fact]
        public async Task Test_Runner_LegacyAgentResponseBypass_RaisesUntaggedEventAsync()
        {
            using FuturesScope _ = new(enabled: false);
            Workflow workflow = BuildAgentResponseWorkflow(designate: null);

            List<WorkflowEvent> events = await RunAsync(workflow, "go");

            AgentResponseEvent emitted = Assert.Single(events.OfType<AgentResponseEvent>());
            Assert.Equal(SourceId, emitted.ExecutorId);
            Assert.Empty(emitted.Tags ?? []);
            Assert.False(emitted.IsIntermediate());
        }

        // F2
        [Fact]
        public async Task Test_Runner_LegacyAgentResponseUpdateBypass_RaisesUntaggedEventAsync()
        {
            using FuturesScope _ = new(enabled: false);
            Workflow workflow = BuildAgentResponseUpdateWorkflow(designate: null);

            List<WorkflowEvent> events = await RunAsync(workflow, "go");

            AgentResponseUpdateEvent emitted = Assert.Single(events.OfType<AgentResponseUpdateEvent>());
            Assert.Empty(emitted.Tags ?? []);
        }

        // F3
        [Fact]
        public async Task Test_Runner_LegacyBypassIgnoresDesignationAsync()
        {
            using FuturesScope _ = new(enabled: false);
            Workflow workflow = BuildAgentResponseWorkflow(static (b, e) => b.WithIntermediateOutputFrom([e]));

            List<WorkflowEvent> events = await RunAsync(workflow, "go");

            AgentResponseEvent emitted = Assert.Single(events.OfType<AgentResponseEvent>());
            Assert.Empty(emitted.Tags ?? []);
            Assert.False(emitted.IsIntermediate());
        }

        // F4
        [Fact]
        public async Task Test_Runner_LegacyPocoIsFilteredAsync()
        {
            using FuturesScope _ = new(enabled: false);
            Workflow workflow = BuildPocoWorkflow(designate: null);

            List<WorkflowEvent> events = await RunAsync(workflow, "go");

            Assert.Empty(events.OfType<WorkflowOutputEvent>() ?? []);
        }

        // F5
        [Fact]
        public async Task Test_Runner_UndesignatedAgentResponseIsFilteredWhenFuturesOnAsync()
        {
            using FuturesScope _ = new(enabled: true);
            Workflow workflow = BuildAgentResponseWorkflow(designate: null);

            List<WorkflowEvent> events = await RunAsync(workflow, "go");

            Assert.Empty(events.OfType<WorkflowOutputEvent>() ?? []);
        }

        // F6
        [Fact]
        public async Task Test_Runner_DesignatedTerminalAgentResponseHasEmptyTagsAsync()
        {
            using FuturesScope _ = new(enabled: true);
            Workflow workflow = BuildAgentResponseWorkflow(static (b, e) => b.WithOutputFrom(e));

            List<WorkflowEvent> events = await RunAsync(workflow, "go");

            AgentResponseEvent emitted = Assert.Single(events.OfType<AgentResponseEvent>());
            Assert.Empty(emitted.Tags ?? []);
            Assert.False(emitted.IsIntermediate());
        }

        // F7
        [Fact]
        public async Task Test_Runner_DesignatedIntermediateAgentResponseHasIntermediateTagAsync()
        {
            using FuturesScope _ = new(enabled: true);
            Workflow workflow = BuildAgentResponseWorkflow(static (b, e) => b.WithIntermediateOutputFrom([e]));

            List<WorkflowEvent> events = await RunAsync(workflow, "go");

            AgentResponseEvent emitted = Assert.Single(events.OfType<AgentResponseEvent>());
            Assert.Equivalent(new[] { OutputTag.Intermediate }, emitted.Tags);
            Assert.True(emitted.IsIntermediate());
        }

        // F8
        [Fact]
        public async Task Test_Runner_DesignatedIntermediateAgentResponseUpdateHasIntermediateTagAsync()
        {
            using FuturesScope _ = new(enabled: true);
            Workflow workflow = BuildAgentResponseUpdateWorkflow(static (b, e) => b.WithIntermediateOutputFrom([e]));

            List<WorkflowEvent> events = await RunAsync(workflow, "go");

            AgentResponseUpdateEvent emitted = Assert.Single(events.OfType<AgentResponseUpdateEvent>());
            Assert.Equivalent(new[] { OutputTag.Intermediate }, emitted.Tags);
            Assert.True(emitted.IsIntermediate());
        }

        // F9
        [Fact]
        public async Task Test_Runner_TagsAccumulateOutputThenIntermediateAsync()
        {
            using FuturesScope _ = new(enabled: true);
            Workflow workflow = BuildAgentResponseWorkflow(static (b, e) =>
            {
                b.WithOutputFrom(e);
                b.WithIntermediateOutputFrom([e]);
            });

            List<WorkflowEvent> events = await RunAsync(workflow, "go");

            AgentResponseEvent emitted = Assert.Single(events.OfType<AgentResponseEvent>());
            Assert.Equivalent(new[] { OutputTag.Intermediate }, emitted.Tags);
            Assert.True(emitted.IsIntermediate());
        }

        // F10
        [Fact]
        public async Task Test_Runner_TagsAccumulateIntermediateThenOutputAsync()
        {
            using FuturesScope _ = new(enabled: true);
            Workflow workflow = BuildAgentResponseWorkflow(static (b, e) =>
            {
                b.WithIntermediateOutputFrom([e]);
                b.WithOutputFrom(e);
            });

            List<WorkflowEvent> events = await RunAsync(workflow, "go");

            AgentResponseEvent emitted = Assert.Single(events.OfType<AgentResponseEvent>());
            Assert.Equivalent(new[] { OutputTag.Intermediate }, emitted.Tags);
            Assert.True(emitted.IsIntermediate());
        }

        // F11
        [Fact]
        public async Task Test_Runner_DesignatedIntermediatePocoHasIntermediateTagAsync()
        {
            using FuturesScope _ = new(enabled: true);
            Workflow workflow = BuildPocoWorkflow(static (b, e) => b.WithIntermediateOutputFrom([e]));

            List<WorkflowEvent> events = await RunAsync(workflow, "go");

            WorkflowOutputEvent emitted = Assert.Single(events.OfType<WorkflowOutputEvent>());
            Assert.False(emitted is AgentResponseEvent);
            Assert.Equivalent(new[] { OutputTag.Intermediate }, emitted.Tags);
            Assert.True(emitted.IsIntermediate());
        }

        // F12
        [Fact]
        public async Task Test_Runner_DesignatedTerminalPocoHasEmptyTagsAsync()
        {
            using FuturesScope _ = new(enabled: true);
            Workflow workflow = BuildPocoWorkflow(static (b, e) => b.WithOutputFrom(e));

            List<WorkflowEvent> events = await RunAsync(workflow, "go");

            WorkflowOutputEvent emitted = Assert.Single(events.OfType<WorkflowOutputEvent>());
            Assert.Empty(emitted.Tags ?? []);
            Assert.False(emitted.IsIntermediate());
        }

        // F13
        [Fact]
        public async Task Test_Runner_RepeatedTerminalDesignationDedupesAsync()
        {
            using FuturesScope _ = new(enabled: true);
            Workflow workflow = BuildAgentResponseWorkflow(static (b, e) =>
            {
                b.WithOutputFrom(e);
                b.WithOutputFrom(e);
            });

            List<WorkflowEvent> events = await RunAsync(workflow, "go");

            AgentResponseEvent emitted = Assert.Single(events.OfType<AgentResponseEvent>());
            Assert.Empty(emitted.Tags ?? []);
        }

        // ---- Executors -----------------------------------------------------------

        internal sealed class YieldAgentResponseExecutor(string id) : Executor(id)
        {
            protected override ProtocolBuilder ConfigureProtocol(ProtocolBuilder protocolBuilder)
                => protocolBuilder.ConfigureRoutes(rb => rb.AddHandler<string, AgentResponse>(this.HandleAsync));

            private ValueTask<AgentResponse> HandleAsync(string input, IWorkflowContext context, CancellationToken cancellationToken)
                => new(SampleResponse(input));
        }

        internal sealed class YieldAgentResponseUpdateExecutor(string id) : Executor(id)
        {
            protected override ProtocolBuilder ConfigureProtocol(ProtocolBuilder protocolBuilder)
                => protocolBuilder.ConfigureRoutes(rb => rb.AddHandler<string, AgentResponseUpdate>(this.HandleAsync));

            private ValueTask<AgentResponseUpdate> HandleAsync(string input, IWorkflowContext context, CancellationToken cancellationToken)
                => new(SampleUpdate(input));
        }

        public sealed record Poco(string Value);

        internal sealed class YieldPocoExecutor(string id) : Executor(id)
        {
            protected override ProtocolBuilder ConfigureProtocol(ProtocolBuilder protocolBuilder)
                => protocolBuilder.ConfigureRoutes(rb => rb.AddHandler<string, Poco>(this.HandleAsync));

            private ValueTask<Poco> HandleAsync(string input, IWorkflowContext context, CancellationToken cancellationToken)
                => new(new Poco(input));
        }
    }
}
