// Copyright (c) Microsoft. All rights reserved.

using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Workflows;

namespace Microsoft.Agents.AI.Hosting.Channels.UnitTests;

public class WorkflowRunnerTests
{
    [Fact]
    public async Task RunAsync_EchoWorkflow_RunsToCompletionAsync()
    {
        // Arrange
        var echo = new EchoExecutor();
        var workflow = new WorkflowBuilder(echo).WithOutputFrom(echo).Build();
        var runner = new WorkflowRunner(workflow);
        var request = new ChannelRequest("test", "message.create", "ping");

        // Act
        var result = await runner.RunAsync(request, CancellationToken.None);

        // Assert
        var typed = Assert.IsType<HostedRunResult<WorkflowRunResult>>(result);
        Assert.Equal(WorkflowRunStatus.Completed, typed.Result.Status);
        Assert.False(string.IsNullOrEmpty(typed.Result.SessionId));
    }

    [Fact]
    public async Task RunAsync_RequestPortWorkflow_ReturnsAwaitingInputAsync()
    {
        // Arrange - a workflow that forwards its input to a RequestPort, pausing for external input
        var port = RequestPort.Create<string, string>("ask");
        var forward = new ForwardExecutor();
        var workflow = new WorkflowBuilder(forward).AddEdge(forward, port).Build();
        var runner = new WorkflowRunner(workflow);
        var request = new ChannelRequest("test", "command.invoke", "hi");

        // Act
        var result = await runner.RunAsync(request, CancellationToken.None);

        // Assert - the RequestInfoEvent surfaces as AwaitingInput with the pending request captured
        var typed = Assert.IsType<HostedRunResult<WorkflowRunResult>>(result);
        Assert.Equal(WorkflowRunStatus.AwaitingInput, typed.Result.Status);
        Assert.NotNull(typed.Result.PendingRequest);
    }

    private sealed class EchoExecutor() : Executor<string, string>("EchoExecutor")
    {
        public override ValueTask<string> HandleAsync(string message, IWorkflowContext context, CancellationToken cancellationToken = default) =>
            ValueTask.FromResult($"echo: {message}");
    }

    private sealed class ForwardExecutor() : Executor<string, string>("ForwardExecutor")
    {
        public override ValueTask<string> HandleAsync(string message, IWorkflowContext context, CancellationToken cancellationToken = default) =>
            ValueTask.FromResult(message);
    }
}
