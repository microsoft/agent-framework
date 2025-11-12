// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using FluentAssertions;

namespace Microsoft.Agents.AI.Workflows.UnitTests;

public sealed class WorkflowHostExecutorTests
{
    [Fact]
    public async Task WorkflowHostExecutor_WithAutoYieldOutputHandlerResultObjectTrue_YieldsSubworkflowOutput()
    {
        // Arrange
        const string outputData = "test output from subworkflow";

        Func<string, IWorkflowContext, CancellationToken, ValueTask> processFunc = (input, context, cancellationToken) => context.YieldOutputAsync(input, cancellationToken);

        ExecutorBinding subworkflowExecutor = processFunc.BindAsExecutor("SubworkflowExecutor", threadsafe: true);
        Workflow subworkflow = new WorkflowBuilder(subworkflowExecutor)
            .WithOutputFrom(subworkflowExecutor)
            .Build();

        ExecutorBinding workflowHostExecutor = subworkflow.BindAsExecutor(
            "HostExecutor",
            new ExecutorOptions
            {
                AutoSendMessageHandlerResultObject = false,
                AutoYieldOutputHandlerResultObject = true
            });

        Func<string, string, ValueTask<Executor>> createOrchestrator = (id, _) => new(new OrchestratorExecutor(id));
        ExecutorBinding orchestrator = createOrchestrator.BindExecutor();

        Workflow workflow = new WorkflowBuilder(orchestrator)
            .AddEdge(orchestrator, workflowHostExecutor)
            .AddEdge(workflowHostExecutor, orchestrator)
            .WithOutputFrom(workflowHostExecutor)
            .Build();

        // Act
        Run workflowRun = await InProcessExecution.RunAsync(workflow, outputData);

        // Assert
        RunStatus status = await workflowRun.GetStatusAsync();
        status.Should().Be(RunStatus.Idle);

        List<WorkflowOutputEvent> outputEvents = workflowRun.OutgoingEvents
            .OfType<WorkflowOutputEvent>()
            .ToList();

        outputEvents.Should().HaveCount(1, "the workflow should produce exactly one output event");
        outputEvents[0].As<string>().Should().Be(outputData, "the output should match the input data");
    }

    [Fact]
    public async Task WorkflowHostExecutor_WithAutoSendMessageHandlerResultObjectTrue_SendsMessageNotYield()
    {
        // Arrange
        const string outputData = "test output from subworkflow";

        Func<string, IWorkflowContext, CancellationToken, ValueTask> processFunc = (input, context, cancellationToken) => context.YieldOutputAsync(input, cancellationToken);

        ExecutorBinding subworkflowExecutor = processFunc.BindAsExecutor("SubworkflowExecutor", threadsafe: true);
        Workflow subworkflow = new WorkflowBuilder(subworkflowExecutor)
            .WithOutputFrom(subworkflowExecutor)
            .Build();

        ExecutorBinding workflowHostExecutor = subworkflow.BindAsExecutor(
            "HostExecutor",
            new ExecutorOptions
            {
                AutoSendMessageHandlerResultObject = true,
                AutoYieldOutputHandlerResultObject = false
            });

        Func<string, string, ValueTask<Executor>> createOrchestrator = (id, _) => new(new OrchestratorExecutor(id));
        ExecutorBinding orchestrator = createOrchestrator.BindExecutor();

        Workflow workflow = new WorkflowBuilder(orchestrator)
            .AddEdge(orchestrator, workflowHostExecutor)
            .AddEdge(workflowHostExecutor, orchestrator)
            .WithOutputFrom(orchestrator)
            .Build();

        // Act
        Run workflowRun = await InProcessExecution.RunAsync(workflow, outputData);

        // Assert
        RunStatus status = await workflowRun.GetStatusAsync();
        status.Should().Be(RunStatus.Idle);

        List<WorkflowOutputEvent> outputEvents = workflowRun.OutgoingEvents
            .OfType<WorkflowOutputEvent>()
            .ToList();

        // With AutoSendMessageHandlerResultObject, the output is sent as a message back to orchestrator, which yields it
        outputEvents.Should().HaveCount(1, "the workflow should produce exactly one output event");
        outputEvents[0].As<string>().Should().Be(outputData, "the output should match the input data");
    }

    [Fact]
    public async Task WorkflowHostExecutor_WithBothOptionsFalse_DoesNotPropagate()
    {
        // Arrange
        const string outputData = "test output from subworkflow";

        Func<string, IWorkflowContext, CancellationToken, ValueTask> processFunc = (input, context, cancellationToken) => context.YieldOutputAsync(input, cancellationToken);

        ExecutorBinding subworkflowExecutor = processFunc.BindAsExecutor("SubworkflowExecutor", threadsafe: true);
        Workflow subworkflow = new WorkflowBuilder(subworkflowExecutor)
            .WithOutputFrom(subworkflowExecutor)
            .Build();

        ExecutorBinding workflowHostExecutor = subworkflow.BindAsExecutor(
            "HostExecutor",
            new ExecutorOptions
            {
                AutoSendMessageHandlerResultObject = false,
                AutoYieldOutputHandlerResultObject = false
            });

        Func<string, string, ValueTask<Executor>> createOrchestrator = (id, _) => new(new OrchestratorExecutor(id));
        ExecutorBinding orchestrator = createOrchestrator.BindExecutor();

        Workflow workflow = new WorkflowBuilder(orchestrator)
            .AddEdge(orchestrator, workflowHostExecutor)
            .AddEdge(workflowHostExecutor, orchestrator)
            .WithOutputFrom(orchestrator)
            .Build();

        // Act
        Run workflowRun = await InProcessExecution.RunAsync(workflow, outputData);

        // Assert
        RunStatus status = await workflowRun.GetStatusAsync();
        status.Should().Be(RunStatus.Idle);

        List<WorkflowOutputEvent> outputEvents = workflowRun.OutgoingEvents
            .OfType<WorkflowOutputEvent>()
            .ToList();

        // When both options are false, the subworkflow output is not propagated
        outputEvents.Should().BeEmpty("no output should be yielded when both options are false");
    }

    private sealed class OrchestratorExecutor : StatefulExecutor<OrchestratorExecutor.State>
    {
        internal sealed class State
        {
            public bool ReceivedInput { get; set; }
            public string? Result { get; set; }
        }

        public OrchestratorExecutor(string id)
            : base(id, () => new State(), declareCrossRunShareable: false)
        {
        }

        protected override RouteBuilder ConfigureRoutes(RouteBuilder routeBuilder)
        {
            return routeBuilder
                .AddHandler<string>(this.HandleInputAsync);
        }

        private async ValueTask HandleInputAsync(string input, IWorkflowContext context, CancellationToken cancellationToken)
        {
            await this.InvokeWithStateAsync(ProcessInputAsync, context, cancellationToken: cancellationToken);

            async ValueTask<State?> ProcessInputAsync(State state, IWorkflowContext context, CancellationToken cancellationToken)
            {
                if (!state.ReceivedInput)
                {
                    state.ReceivedInput = true;
                    await context.SendMessageAsync(input, cancellationToken: cancellationToken);
                }
                else
                {
                    state.Result = input;
                    await context.YieldOutputAsync(input, cancellationToken);
                }

                return state;
            }
        }
    }
}
