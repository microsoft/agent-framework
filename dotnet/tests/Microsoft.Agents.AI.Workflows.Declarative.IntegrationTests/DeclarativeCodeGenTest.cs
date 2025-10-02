// Copyright (c) Microsoft. All rights reserved.

using System;
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
public sealed class DeclarativeCodeGenTest(ITestOutputHelper output) : WorkflowTest(output)
{
    [Theory]
    [InlineData("SendActivity.yaml", "SendActivity.json")]
    [InlineData("InvokeAgent.yaml", "InvokeAgent.json")]
    [InlineData("ConversationMessages.yaml", "ConversationMessages.json")]
    public Task ValidateCaseAsync(string workflowFileName, string testcaseFileName) =>
        this.RunWorkflowAsync(Path.Combine(Environment.CurrentDirectory, "Workflows", workflowFileName), testcaseFileName);

    [Theory]
    [InlineData("Marketing.yaml", "Marketing.json")]
    [InlineData("MathChat.yaml", "MathChat.json")]
    [InlineData("DeepResearch.yaml", "DeepResearch.json", Skip = "Long running")]
    [InlineData("HumanInLoop.yaml", "HumanInLoop.json", Skip = "Needs test support")]
    public Task ValidateScenarioAsync(string workflowFileName, string testcaseFileName) =>
        this.RunWorkflowAsync(Path.Combine(GetRepoFolder(), "workflow-samples", workflowFileName), testcaseFileName);

    protected override async Task RunAndVerifyAsync<TInput>(Testcase testcase, string workflowPath, DeclarativeWorkflowOptions workflowOptions)
    {
        const string WorkflowNamespace = "Test.WorkflowProviders";
        const string WorkflowPrefix = "Test";

        string workflowProviderCode = DeclarativeWorkflowBuilder.Eject(workflowPath, DeclarativeWorkflowLanguage.CSharp, WorkflowNamespace, WorkflowPrefix);
        try
        {
            WorkflowEvents workflowEvents = await WorkflowHarness.RunCodeAsync(workflowProviderCode, $"{WorkflowPrefix}WorkflowProvider", WorkflowNamespace, workflowOptions, (TInput)GetInput<TInput>(testcase));
            foreach (ExecutorEvent invokeEvent in workflowEvents.ExecutorInvokeEvents)
            {
                this.Output.WriteLine($"EXEC: {invokeEvent.ExecutorId}");
            }

            Assert.Empty(workflowEvents.ActionInvokeEvents);
            Assert.Empty(workflowEvents.ActionCompleteEvents);
            AssertWorkflow.EventCounts(workflowEvents.ExecutorInvokeEvents.Count - 2, testcase);
            AssertWorkflow.EventCounts(workflowEvents.ExecutorCompleteEvents.Count - 2, testcase);
            AssertWorkflow.EventSequence(workflowEvents.ExecutorInvokeEvents.Select(e => e.ExecutorId), testcase);
        }
        finally
        {
            this.Output.WriteLine($"CODE:\n{workflowProviderCode}");
        }
    }
}
