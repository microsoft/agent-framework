// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using FluentAssertions;
using Microsoft.Agents.Workflows.Checkpointing;
using Microsoft.Agents.Workflows.Sample;
using Microsoft.Agents.Workflows.Specialized;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.AI.Agents;

namespace Microsoft.Agents.Workflows.UnitTests;

public class RepresentationTests
{
    private sealed class TestExecutor : Executor
    {
        protected override RouteBuilder ConfigureRoutes(RouteBuilder routeBuilder) => routeBuilder;
    }

    private sealed class TestAgent : AIAgent
    {
        public override AgentThread GetNewThread()
            => throw new NotImplementedException();

        public override AgentThread DeserializeThread(JsonElement serializedThread, JsonSerializerOptions? jsonSerializerOptions = null)
            => throw new NotImplementedException();

        public override Task<AgentRunResponse> RunAsync(IEnumerable<ChatMessage> messages, AgentThread? thread = null, AgentRunOptions? options = null, CancellationToken cancellationToken = default) =>
            throw new NotImplementedException();

        public override IAsyncEnumerable<AgentRunResponseUpdate> RunStreamingAsync(IEnumerable<ChatMessage> messages, AgentThread? thread = null, AgentRunOptions? options = null, CancellationToken cancellationToken = default) =>
            throw new NotImplementedException();
    }

    private static InputPort TestInputPort =>
        InputPort.Create<FunctionCallContent, FunctionResultContent>("ExternalFunction");

    private static async ValueTask RunExecutorishInfoMatchTestAsync(ExecutorIsh target)
    {
        ExecutorRegistration registration = target.Registration;
        ExecutorInfo info = registration.ToExecutorInfo();

        info.IsMatch(await registration.ProviderAsync()).Should().BeTrue();
    }

    [Fact]
    public async Task Test_Executorish_InfosAsync()
    {
        int testsRun = 0;
        await RunExecutorishTestAsync(new TestExecutor());
        await RunExecutorishTestAsync(TestInputPort);
        await RunExecutorishTestAsync(new TestAgent());

        Func<int, IWorkflowContext, CancellationToken, ValueTask> function = MessageHandlerAsync;
        await RunExecutorishTestAsync(function.AsExecutor("FunctionExecutor"));

        if (Enum.GetValues(typeof(ExecutorIsh.Type)).Length > testsRun + 1)
        {
            Assert.Fail("Not all ExecutorIsh types were tested.");
        }

        async ValueTask RunExecutorishTestAsync(ExecutorIsh executorish)
        {
            await RunExecutorishInfoMatchTestAsync(executorish);
            testsRun++;
        }

        async ValueTask MessageHandlerAsync(int message, IWorkflowContext workflowContext, CancellationToken cancellation = default)
        {
        }
    }

    [Fact]
    public async Task Test_SpecializedExecutor_InfosAsync()
    {
        await RunExecutorishInfoMatchTestAsync(new AIAgentHostExecutor(new TestAgent()));
        await RunExecutorishInfoMatchTestAsync(new RequestInfoExecutor(TestInputPort));

        OutputCollectorExecutor<ChatMessage, IEnumerable<ChatMessage>> outputCollector = new(StreamingAggregators.Union<ChatMessage>());
        await RunExecutorishInfoMatchTestAsync(outputCollector);
    }

    private static string Source(int id) => $"Source/{id}";
    private static string Sink(int id) => $"Sink/{id}";

    private static Func<object?, bool> Condition() => Condition<object>();
    private static Func<TIn?, bool> Condition<TIn>() => _ => true;

    private static Func<object?, int, IEnumerable<int>> EdgeAssigner() => EdgeAssigner<object>();
    private static Func<TIn?, int, IEnumerable<int>> EdgeAssigner<TIn>() => (_, _) => [];

    [Fact]
    public void Test_EdgeInfos()
    {
        int edgeId = 0;

        // Direct Edges
        Edge directEdgeNoCondition = new(new DirectEdgeData(Source(1), Sink(2), TakeEdgeId()));
        RunEdgeInfoMatchTest(directEdgeNoCondition);

        Edge directEdgeNoCondition2 = new(new DirectEdgeData(Source(1), Sink(2), TakeEdgeId()));
        RunEdgeInfoMatchTest(directEdgeNoCondition, directEdgeNoCondition2);

        Edge directEdgeNoCondition3 = new(new DirectEdgeData(Source(3), Sink(4), TakeEdgeId()));
        RunEdgeInfoMatchTest(directEdgeNoCondition, directEdgeNoCondition3, expect: false);

        Edge directEdgeWithCondition = new(new DirectEdgeData(Source(3), Sink(4), TakeEdgeId(), Condition()));
        RunEdgeInfoMatchTest(directEdgeWithCondition);
        RunEdgeInfoMatchTest(directEdgeNoCondition2, directEdgeWithCondition, expect: false);
        RunEdgeInfoMatchTest(directEdgeNoCondition3, directEdgeWithCondition, expect: false);

        // FanOut Edges
        Edge fanOutEdgeNoAssigner = new(new FanOutEdgeData(Source(1), [Sink(2), Sink(3), Sink(4)], TakeEdgeId()));
        RunEdgeInfoMatchTest(fanOutEdgeNoAssigner);

        Edge fanOutEdgeNoAssigner2 = new(new FanOutEdgeData(Source(1), [Sink(2), Sink(3), Sink(4)], TakeEdgeId()));
        RunEdgeInfoMatchTest(fanOutEdgeNoAssigner, fanOutEdgeNoAssigner2);

        Edge fanOutEdgeNoAssigner3 = new(new FanOutEdgeData(Source(1), [Sink(3), Sink(4), Sink(2)], TakeEdgeId()));
        RunEdgeInfoMatchTest(fanOutEdgeNoAssigner, fanOutEdgeNoAssigner3, expect: false); // Order matters (though without Assigner maybe it shouldn't?)

        Edge fanOutEdgeNoAssigner4 = new(new FanOutEdgeData(Source(1), [Sink(2), Sink(3), Sink(5)], TakeEdgeId()));
        Edge fanOutEdgeNoAssigner5 = new(new FanOutEdgeData(Source(2), [Sink(2), Sink(3), Sink(4)], TakeEdgeId()));
        RunEdgeInfoMatchTest(fanOutEdgeNoAssigner, fanOutEdgeNoAssigner4, expect: false); // Identity matters
        RunEdgeInfoMatchTest(fanOutEdgeNoAssigner, fanOutEdgeNoAssigner5, expect: false);

        Edge fanOutEdgeWithAssigner = new(new FanOutEdgeData(Source(1), [Sink(2), Sink(3), Sink(4)], TakeEdgeId(), EdgeAssigner()));
        RunEdgeInfoMatchTest(fanOutEdgeWithAssigner);

        // FanIn Edges
        Edge fanInEdge = new(new FanInEdgeData([Source(1), Source(2), Source(3)], Sink(1), TakeEdgeId()));
        RunEdgeInfoMatchTest(fanInEdge);

        Edge fanInEdge2 = new(new FanInEdgeData([Source(1), Source(2), Source(3)], Sink(1), TakeEdgeId()));
        RunEdgeInfoMatchTest(fanInEdge, fanInEdge2);

        Edge fanInEdge3 = new(new FanInEdgeData([Source(2), Source(3), Source(1)], Sink(1), TakeEdgeId()));
        RunEdgeInfoMatchTest(fanInEdge, fanInEdge3, expect: false); // Order matters (though for FanIn maybe it shouldn't?)

        Edge fanInEdge4 = new(new FanInEdgeData([Source(1), Source(2), Source(4)], Sink(1), TakeEdgeId()));
        Edge fanInEdge5 = new(new FanInEdgeData([Source(1), Source(2), Source(3)], Sink(2), TakeEdgeId()));
        RunEdgeInfoMatchTest(fanInEdge, fanInEdge4, expect: false); // Identity matters
        RunEdgeInfoMatchTest(fanInEdge, fanInEdge5, expect: false);

        static void RunEdgeInfoMatchTest(Edge edge, Edge? comparatorEdge = null, bool expect = true)
        {
            comparatorEdge ??= edge;

            EdgeInfo info = edge.ToEdgeInfo();
            info.IsMatch(comparatorEdge).Should().Be(expect);
        }

        EdgeId TakeEdgeId() => new(edgeId++);
    }

    [Fact]
    public void Test_Sample_WorkflowInfos()
    {
        RunWorkflowInfoMatchTest(Step1EntryPoint.WorkflowInstance);
        RunWorkflowInfoMatchTest(Step2EntryPoint.WorkflowInstance);
        RunWorkflowInfoMatchTest(Step3EntryPoint.WorkflowInstance);
        RunWorkflowInfoMatchTest(Step4EntryPoint.WorkflowInstance);
        // Step 5 reuses the workflow from Step 4, so we don't need to test it separately.
        RunWorkflowInfoMatchTest(Step6EntryPoint.CreateWorkflow(2));
        // Step 7 reuses the workflow from Step 6, so we don't need to test it separately.

        RunWorkflowInfoMatchTest(Step1EntryPoint.WorkflowInstance, Step2EntryPoint.WorkflowInstance, expect: false);

        static void RunWorkflowInfoMatchTest<TInput>(Workflow<TInput> workflow, Workflow<TInput>? comparator = null, bool expect = true)
        {
            comparator ??= workflow;

            WorkflowInfo info = workflow.ToWorkflowInfo();
            info.IsMatch(comparator).Should().Be(expect);
        }
    }
}
