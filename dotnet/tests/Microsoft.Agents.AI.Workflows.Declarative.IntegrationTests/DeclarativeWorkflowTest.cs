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
public sealed class DeclarativeWorkflowTest(ITestOutputHelper output) : WorkflowTest(output)
{
    [Theory]
    [InlineData("SendActivity.yaml", "SendActivity.json")]
    [InlineData("InvokeAgent.yaml", "InvokeAgent.json")]
    [InlineData("InvokeAgent.yaml", "InvokeAgent.json", true)]
    [InlineData("ConversationMessages.yaml", "ConversationMessages.json")]
    [InlineData("ConversationMessages.yaml", "ConversationMessages.json", true)]
    public Task ValidateCaseAsync(string workflowFileName, string testcaseFileName, bool externalConveration = false) =>
        this.RunWorkflowAsync(Path.Combine(Environment.CurrentDirectory, "Workflows", workflowFileName), testcaseFileName, externalConveration);

    [Theory]
    [InlineData("Marketing.yaml", "Marketing.json")]
    [InlineData("Marketing.yaml", "Marketing.json", true)]
    [InlineData("MathChat.yaml", "MathChat.json", true)]
    [InlineData("DeepResearch.yaml", "DeepResearch.json", Skip = "Long running")]
    [InlineData("HumanInLoop.yaml", "HumanInLoop.json")]
    public Task ValidateScenarioAsync(string workflowFileName, string testcaseFileName, bool externalConveration = false) =>
        this.RunWorkflowAsync(Path.Combine(GetRepoFolder(), "workflow-samples", workflowFileName), testcaseFileName, externalConveration);

    protected override async Task RunAndVerifyAsync<TInput>(Testcase testcase, string workflowPath, DeclarativeWorkflowOptions workflowOptions)
    {
        Workflow workflow = DeclarativeWorkflowBuilder.Build<TInput>(workflowPath, workflowOptions);

        WorkflowHarness harness = new(workflow, runId: Path.GetFileNameWithoutExtension(workflowPath));
        WorkflowEvents workflowEvents = await harness.RunTestcaseAsync(testcase, (TInput)GetInput<TInput>(testcase)).ConfigureAwait(false);

        Assert.NotEmpty(workflowEvents.ExecutorInvokeEvents);
        Assert.NotEmpty(workflowEvents.ExecutorCompleteEvents);
        AssertWorkflow.Conversation(workflowOptions.ConversationId, workflowEvents.ConversationEvents, testcase);
        AssertWorkflow.Responses(workflowEvents.AgentResponseEvents, testcase);
        await AssertWorkflow.MessagesAsync(
            GetConversationId(workflowOptions.ConversationId, workflowEvents.ConversationEvents),
            testcase,
            workflowOptions.AgentProvider);
        AssertWorkflow.EventCounts(workflowEvents.ActionInvokeEvents.Count, testcase);
        AssertWorkflow.EventCounts(workflowEvents.ActionCompleteEvents.Count, testcase, isCompletion: true);
        AssertWorkflow.EventSequence(workflowEvents.ActionInvokeEvents.Select(e => e.ActionId), testcase);
    }
}
