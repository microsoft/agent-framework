// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using FluentAssertions;
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

            AgentResponseEvent emitted = events.OfType<AgentResponseEvent>().Should().ContainSingle().Subject;
            emitted.ExecutorId.Should().Be(SourceId);
            emitted.Tags.Should().BeEmpty("legacy bypass attaches no tags");
            emitted.IsIntermediate().Should().BeFalse();
        }

        // F2
        [Fact]
        public async Task Test_Runner_LegacyAgentResponseUpdateBypass_RaisesUntaggedEventAsync()
        {
            using FuturesScope _ = new(enabled: false);
            Workflow workflow = BuildAgentResponseUpdateWorkflow(designate: null);

            List<WorkflowEvent> events = await RunAsync(workflow, "go");

            AgentResponseUpdateEvent emitted = events.OfType<AgentResponseUpdateEvent>().Should().ContainSingle().Subject;
            emitted.Tags.Should().BeEmpty();
        }

        // F3
        [Fact]
        public async Task Test_Runner_LegacyBypassIgnoresDesignationAsync()
        {
            using FuturesScope _ = new(enabled: false);
            Workflow workflow = BuildAgentResponseWorkflow(static (b, e) => b.WithIntermediateOutputFrom([e]));

            List<WorkflowEvent> events = await RunAsync(workflow, "go");

            AgentResponseEvent emitted = events.OfType<AgentResponseEvent>().Should().ContainSingle().Subject;
            emitted.Tags.Should().BeEmpty("legacy bypass ignores the designation entirely");
            emitted.IsIntermediate().Should().BeFalse("legacy bypass does not propagate tags");
        }

        // F4
        [Fact]
        public async Task Test_Runner_LegacyPocoIsFilteredAsync()
        {
            using FuturesScope _ = new(enabled: false);
            Workflow workflow = BuildPocoWorkflow(designate: null);

            List<WorkflowEvent> events = await RunAsync(workflow, "go");

            events.OfType<WorkflowOutputEvent>().Should().BeEmpty("POCO outputs always go through the filter; undesignated source is dropped");
        }

        // F5
        [Fact]
        public async Task Test_Runner_UndesignatedAgentResponseIsFilteredWhenFuturesOnAsync()
        {
            using FuturesScope _ = new(enabled: true);
            Workflow workflow = BuildAgentResponseWorkflow(designate: null);

            List<WorkflowEvent> events = await RunAsync(workflow, "go");

            events.OfType<WorkflowOutputEvent>().Should().BeEmpty(
                "with the future on, AgentResponse must be designated to surface");
        }

        // F6
        [Fact]
        public async Task Test_Runner_DesignatedTerminalAgentResponseHasEmptyTagsAsync()
        {
            using FuturesScope _ = new(enabled: true);
            Workflow workflow = BuildAgentResponseWorkflow(static (b, e) => b.WithOutputFrom(e));

            List<WorkflowEvent> events = await RunAsync(workflow, "go");

            AgentResponseEvent emitted = events.OfType<AgentResponseEvent>().Should().ContainSingle().Subject;
            emitted.Tags.Should().BeEmpty("terminal designation carries no tag");
            emitted.IsIntermediate().Should().BeFalse();
        }

        // F7
        [Fact]
        public async Task Test_Runner_DesignatedIntermediateAgentResponseHasIntermediateTagAsync()
        {
            using FuturesScope _ = new(enabled: true);
            Workflow workflow = BuildAgentResponseWorkflow(static (b, e) => b.WithIntermediateOutputFrom([e]));

            List<WorkflowEvent> events = await RunAsync(workflow, "go");

            AgentResponseEvent emitted = events.OfType<AgentResponseEvent>().Should().ContainSingle().Subject;
            emitted.Tags.Should().BeEquivalentTo(new[] { OutputTag.Intermediate });
            emitted.IsIntermediate().Should().BeTrue();
        }

        // F8
        [Fact]
        public async Task Test_Runner_DesignatedIntermediateAgentResponseUpdateHasIntermediateTagAsync()
        {
            using FuturesScope _ = new(enabled: true);
            Workflow workflow = BuildAgentResponseUpdateWorkflow(static (b, e) => b.WithIntermediateOutputFrom([e]));

            List<WorkflowEvent> events = await RunAsync(workflow, "go");

            AgentResponseUpdateEvent emitted = events.OfType<AgentResponseUpdateEvent>().Should().ContainSingle().Subject;
            emitted.Tags.Should().BeEquivalentTo(new[] { OutputTag.Intermediate });
            emitted.IsIntermediate().Should().BeTrue();
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

            AgentResponseEvent emitted = events.OfType<AgentResponseEvent>().Should().ContainSingle().Subject;
            emitted.Tags.Should().BeEquivalentTo(new[] { OutputTag.Intermediate },
                "terminal+intermediate union is {{ Intermediate }} (terminal contributes the entry but no tag)");
            emitted.IsIntermediate().Should().BeTrue();
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

            AgentResponseEvent emitted = events.OfType<AgentResponseEvent>().Should().ContainSingle().Subject;
            emitted.Tags.Should().BeEquivalentTo(new[] { OutputTag.Intermediate }, "designation order is irrelevant");
            emitted.IsIntermediate().Should().BeTrue();
        }

        // F11
        [Fact]
        public async Task Test_Runner_DesignatedIntermediatePocoHasIntermediateTagAsync()
        {
            using FuturesScope _ = new(enabled: true);
            Workflow workflow = BuildPocoWorkflow(static (b, e) => b.WithIntermediateOutputFrom([e]));

            List<WorkflowEvent> events = await RunAsync(workflow, "go");

            WorkflowOutputEvent emitted = events.OfType<WorkflowOutputEvent>().Should().ContainSingle().Subject;
            emitted.Should().NotBeOfType<AgentResponseEvent>();
            emitted.Tags.Should().BeEquivalentTo(new[] { OutputTag.Intermediate });
            emitted.IsIntermediate().Should().BeTrue();
        }

        // F12
        [Fact]
        public async Task Test_Runner_DesignatedTerminalPocoHasEmptyTagsAsync()
        {
            using FuturesScope _ = new(enabled: true);
            Workflow workflow = BuildPocoWorkflow(static (b, e) => b.WithOutputFrom(e));

            List<WorkflowEvent> events = await RunAsync(workflow, "go");

            WorkflowOutputEvent emitted = events.OfType<WorkflowOutputEvent>().Should().ContainSingle().Subject;
            emitted.Tags.Should().BeEmpty();
            emitted.IsIntermediate().Should().BeFalse();
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

            AgentResponseEvent emitted = events.OfType<AgentResponseEvent>().Should().ContainSingle().Subject;
            emitted.Tags.Should().BeEmpty("repeated terminal designation contributes no tag");
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
