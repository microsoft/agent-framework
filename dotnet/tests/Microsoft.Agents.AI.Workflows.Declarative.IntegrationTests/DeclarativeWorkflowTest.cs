// Copyright (c) Microsoft. All rights reserved.

using System.IO;
using System.Linq;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Workflows.Declarative.IntegrationTests.Framework;
using Xunit.Abstractions;

namespace Microsoft.Agents.AI.Workflows.Declarative.IntegrationTests;

/// <summary>
/// Tests execution of workflow created by <see cref="DeclarativeWorkflowBuilder"/>.
/// </summary>
[Collection("Global")]
public sealed class DeclarativeWorkflowTest(ITestOutputHelper output) : WorkflowTest(output)
{
    [Theory]
    [InlineData("SendActivity.yaml", "SendActivity.json", Skip = "Needs configuration")]
    [InlineData("InvokeAgent.yaml", "InvokeAgent.json", Skip = "Needs configuration")]
    [InlineData("ConversationMessages.yaml", "ConversationMessages.json", Skip = "Needs configuration")]
    public Task ValidateCaseAsync(string workflowFileName, string testcaseFileName) =>
        this.RunWorkflowAsync(Path.Combine("Workflows", workflowFileName), testcaseFileName);

    [Theory]
    [InlineData("Marketing.yaml", "Marketing.json", Skip = "Needs configuration")]
    [InlineData("MathChat.yaml", "MathChat.json", Skip = "Needs configuration")]
    [InlineData("DeepResearch.yaml", "DeepResearch.json", Skip = "Needs configuration")]
    [InlineData("HumanInLoop.yaml", "HumanInLoop.json", Skip = "Needs test support")]
    public Task ValidateScenarioAsync(string workflowFileName, string testcaseFileName) =>
        this.RunWorkflowAsync(Path.Combine(GetRepoFolder(), "workflow-samples", workflowFileName), testcaseFileName);

    protected override async Task RunAndVerifyAsync<TInput>(Testcase testcase, string workflowPath, DeclarativeWorkflowOptions workflowOptions)
    {
        Workflow workflow = DeclarativeWorkflowBuilder.Build<TInput>(workflowPath, workflowOptions);

        WorkflowEvents workflowEvents = await WorkflowHarness.RunAsync(workflow, (TInput)GetInput<TInput>(testcase));
        foreach (DeclarativeActionInvokedEvent actionInvokeEvent in workflowEvents.ActionInvokeEvents)
        {
            this.Output.WriteLine($"ACTION: {actionInvokeEvent.ActionId} [{actionInvokeEvent.ActionType}]");
        }

        Assert.NotEmpty(workflowEvents.ExecutorInvokeEvents);
        Assert.NotEmpty(workflowEvents.ExecutorCompleteEvents);
        AssertWorkflow.EventCounts(workflowEvents.ActionInvokeEvents.Count, testcase);
        AssertWorkflow.EventCounts(workflowEvents.ActionCompleteEvents.Count, testcase);
        AssertWorkflow.EventSequence(workflowEvents.ActionInvokeEvents.Select(e => e.ActionId), testcase);
    }
}
