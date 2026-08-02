// Copyright (c) Microsoft. All rights reserved.

using System.Threading;
using System.Threading.Tasks;
using FluentAssertions;
using Microsoft.Agents.AI.Workflows.Checkpointing;
using Microsoft.Agents.AI.Workflows.Execution;
using Microsoft.Agents.AI.Workflows.InProc;

namespace Microsoft.Agents.AI.Workflows.UnitTests;

public class ExternalResponsePortCorrelationTests
{
    private const string PortAId = "portA";
    private const string PortBId = "portB";
    private const string SinkId = "sink";

    private static (Workflow Workflow, RequestPort PortA, RequestPort PortB) BuildTwoPortWorkflow()
    {
        // Both ports must be registered so a forged PortInfo.PortId is routable past the EdgeMap;
        // this isolates the runner-context gate as the only check that can reject the forgery.
        RequestPort portA = RequestPort.Create<string, int>(PortAId);
        RequestPort portB = RequestPort.Create<string, int>(PortBId);
        ForwardMessageExecutor<int> sink = new(SinkId);

        Workflow workflow = new WorkflowBuilder(portA)
            .AddEdge(portA, sink)
            .AddEdge(portB, sink)
            .Build(validateOrphans: false);

        return (workflow, portA, portB);
    }

    [Fact]
    public async Task AddExternalResponseAsync_RejectsForgedPortIdAsync()
    {
        // Arrange
        (Workflow workflow, RequestPort portA, RequestPort portB) = BuildTwoPortWorkflow();
        InProcessRunner runner = InProcessRunner.CreateTopLevelRunner(workflow, checkpointManager: null);

        ExternalRequest pending = ExternalRequest.Create(portA, "data");
        await runner.RunContext.PostAsync(pending);

        // Forged: claims portB but reuses portA's RequestId. Identical response types isolate PortId as the only signal.
        ExternalResponse forged = new(portB.ToPortInfo(), pending.RequestId, new PortableValue(42));

        // Act
        await runner.RunContext.AddExternalResponseAsync(forged);

        // Assert: validation fires when the queued delivery is drained.
        var act = async () => await runner.RunContext.AdvanceAsync(CancellationToken.None);
        var exception = await act.Should().ThrowAsync<System.InvalidOperationException>();

        string message = exception.Which.Message;
        message.Should().Contain($"'{PortBId}'").And.Contain(pending.RequestId).And.NotContain($"'{PortAId}'");

        // Pending request survives the rejection so the legitimate responder can still complete it.
        ((ISuperStepRunner)runner).HasUnservicedRequests.Should().BeTrue();
    }

    [Fact]
    public async Task AddExternalResponseAsync_AllowsLegitimateResponseAfterRejectedForgeryAsync()
    {
        (Workflow workflow, RequestPort portA, RequestPort portB) = BuildTwoPortWorkflow();
        InProcessRunner runner = InProcessRunner.CreateTopLevelRunner(workflow, checkpointManager: null);

        ExternalRequest pending = ExternalRequest.Create(portA, "data");
        await runner.RunContext.PostAsync(pending);

        ExternalResponse forged = new(portB.ToPortInfo(), pending.RequestId, new PortableValue(42));
        await runner.RunContext.AddExternalResponseAsync(forged);

        var rejectAct = async () => await runner.RunContext.AdvanceAsync(CancellationToken.None);
        await rejectAct.Should().ThrowAsync<System.InvalidOperationException>();

        // Legitimate responder retries with the correct PortInfo.
        ExternalResponse legitimate = pending.CreateResponse(42);
        await runner.RunContext.AddExternalResponseAsync(legitimate);

        var legitimateAct = async () => await runner.RunContext.AdvanceAsync(CancellationToken.None);

        await legitimateAct.Should().NotThrowAsync();
        ((ISuperStepRunner)runner).HasUnservicedRequests.Should().BeFalse();
    }

    [Fact]
    public async Task AddExternalResponseAsync_AllowsMatchingPortIdAsync()
    {
        // Baseline: matched-port response is accepted and consumes the pending request.
        (Workflow workflow, RequestPort portA, _) = BuildTwoPortWorkflow();
        InProcessRunner runner = InProcessRunner.CreateTopLevelRunner(workflow, checkpointManager: null);

        ExternalRequest pending = ExternalRequest.Create(portA, "data");
        await runner.RunContext.PostAsync(pending);

        ExternalResponse legitimate = pending.CreateResponse(42);

        await runner.RunContext.AddExternalResponseAsync(legitimate);

        var act = async () => await runner.RunContext.AdvanceAsync(CancellationToken.None);
        await act.Should().NotThrowAsync();

        ((ISuperStepRunner)runner).HasUnservicedRequests.Should().BeFalse();
    }

    [Fact]
    public async Task AddExternalResponseAsync_RejectsUnknownRequestIdAsync()
    {
        // Regression: unknown RequestId still throws with the original "No pending request" message.
        (Workflow workflow, RequestPort portA, _) = BuildTwoPortWorkflow();
        InProcessRunner runner = InProcessRunner.CreateTopLevelRunner(workflow, checkpointManager: null);

        ExternalResponse stray = new(portA.ToPortInfo(), "no-such-request", new PortableValue(42));

        await runner.RunContext.AddExternalResponseAsync(stray);

        var act = async () => await runner.RunContext.AdvanceAsync(CancellationToken.None);
        var exception = await act.Should().ThrowAsync<System.InvalidOperationException>();
        exception.Which.Message.Should().Contain("No pending request with ID no-such-request");
    }
}
