// Copyright (c) Microsoft. All rights reserved.

using System.Threading.Tasks;
using Microsoft.Agents.Workflows.Declarative.IntegrationTests.Framework;
using Xunit.Abstractions;

namespace Microsoft.Agents.Workflows.Declarative.IntegrationTests;

/// <summary>
/// Tests execution of workflow created by <see cref="DeclarativeWorkflowBuilder"/>.
/// </summary>
[Collection("Global")]
public sealed class DeclarativeWorkflowTest(ITestOutputHelper output) : WorkflowTest(output)
{
    [Theory]
    [InlineData("SendActivity.yaml", "SendActivity.json")]
    [InlineData("InvokeAgent.yaml", "InvokeAgent.json")]
    [InlineData("ConversationMessages.yaml", "ConversationMessages.json")]
    public Task ValidateAsync(string workflowFileName, string testcaseFileName) =>
        this.RunWorkflowAsync(workflowFileName, testcaseFileName);

    protected override async Task RunAndVerifyAsync<TInput>(Testcase testcase, string workflowPath, DeclarativeWorkflowOptions workflowOptions)
    {
        Workflow workflow = DeclarativeWorkflowBuilder.Build<TInput>(workflowPath, workflowOptions);

        WorkflowEvents workflowEvents = await WorkflowHarness.RunAsync(workflow, (TInput)GetInput<TInput>(testcase));
        foreach (DeclarativeActionInvokedEvent actionInvokeEvent in workflowEvents.ActionInvokeEvents)
        {
            this.Output.WriteLine($"ACTION: {actionInvokeEvent.ActionId} [{actionInvokeEvent.ActionType}]");
        }

        Assert.Equal(testcase.Validation.ActionCount, workflowEvents.ActionInvokeEvents.Count);
        Assert.Equal(testcase.Validation.ActionCount, workflowEvents.ActionCompleteEvents.Count);
    }
}
