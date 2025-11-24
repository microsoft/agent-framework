// Copyright (c) Microsoft. All rights reserved.

using System;
using System.IO;
using System.Linq;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Workflows.Declarative.IntegrationTests.Agents;
using Microsoft.Agents.AI.Workflows.Declarative.IntegrationTests.Framework;
using Xunit.Abstractions;

namespace Microsoft.Agents.AI.Workflows.Declarative.IntegrationTests;

/// <summary>
/// Tests execution of workflow created by <see cref="DeclarativeWorkflowBuilder"/>.
/// </summary>
public sealed class DeclarativeWorkflowTest(ITestOutputHelper output) : WorkflowTest(output)
{
    [Theory]
    [InlineData("CheckSystem.yaml", "CheckSystem.json")]
    [InlineData("ConversationMessages.yaml", "ConversationMessages.json")]
    [InlineData("ConversationMessages.yaml", "ConversationMessages.json", true)]
    [InlineData("InputArguments.yaml", "InputArguments.json")]
    [InlineData("InvokeAgent.yaml", "InvokeAgent.json")]
    [InlineData("InvokeAgent.yaml", "InvokeAgent.json", true)]
    [InlineData("SendActivity.yaml", "SendActivity.json")]
    public Task ValidateCaseAsync(string workflowFileName, string testcaseFileName, bool externalConveration = false) =>
        this.RunWorkflowAsync(GetWorkflowPath(workflowFileName, isSample: false), testcaseFileName, externalConveration);

    [Theory]
    [InlineData("Marketing.yaml", "Marketing.json")]
    [InlineData("Marketing.yaml", "Marketing.json", true)]
    [InlineData("MathChat.yaml", "MathChat.json", true)]
    [InlineData("DeepResearch.yaml", "DeepResearch.json", Skip = "Long running")]
    public Task ValidateScenarioAsync(string workflowFileName, string testcaseFileName, bool externalConveration = false) =>
        this.RunWorkflowAsync(GetWorkflowPath(workflowFileName, isSample: true), testcaseFileName, externalConveration);

    [Theory]
    [InlineData("ConfirmInput.yaml", "ConfirmInput.json", false)]
    [InlineData("RequestExternalInput.yaml", "RequestExternalInput.json", false)]
    public Task ValidateMultiTurnAsync(string workflowFileName, string testcaseFileName, bool isSample) =>
        this.RunWorkflowAsync(GetWorkflowPath(workflowFileName, isSample), testcaseFileName, useJsonCheckpoint: true);

    private static string GetWorkflowPath(string workflowFileName, bool isSample) =>
        isSample
            ? Path.Combine(GetRepoFolder(), "workflow-samples", workflowFileName)
            : Path.Combine(Environment.CurrentDirectory, "Workflows", workflowFileName);

    protected override async Task RunAndVerifyAsync<TInput>(Testcase testcase, string workflowPath, DeclarativeWorkflowOptions workflowOptions, TInput input, bool useJsonCheckpoint)
    {
        AgentProvider agentProvider = AgentProvider.Create(this.Configuration, Path.GetFileNameWithoutExtension(workflowPath));
        await agentProvider.CreateAgentsAsync().ConfigureAwait(false);

        Workflow workflow = DeclarativeWorkflowBuilder.Build<TInput>(workflowPath, workflowOptions);

        WorkflowHarness harness = new(workflow, runId: Path.GetFileNameWithoutExtension(workflowPath));
        WorkflowEvents workflowEvents = await harness.RunTestcaseAsync(testcase, input, useJsonCheckpoint).ConfigureAwait(false);

        // Verify executor events are present
        Assert.NotEmpty(workflowEvents.ExecutorInvokeEvents);
        Assert.NotEmpty(workflowEvents.ExecutorCompleteEvents);
        // Verify the associated conversations
        AssertWorkflow.Conversation(workflowEvents.ConversationEvents, testcase);
        // Verify the agent responses
        AssertWorkflow.Responses(workflowEvents.AgentResponseEvents, testcase);
        // Verify the messages on the workflow conversation
        await AssertWorkflow.MessagesAsync(
            GetConversationId(workflowOptions.ConversationId, workflowEvents.ConversationEvents),
            testcase,
            workflowOptions.AgentProvider);
        // Verify action events
        AssertWorkflow.EventCounts(workflowEvents.ActionInvokeEvents.Count, testcase);
        AssertWorkflow.EventCounts(workflowEvents.ActionCompleteEvents.Count, testcase, isCompletion: true);
        // Verify action sequences
        AssertWorkflow.EventSequence(workflowEvents.ActionInvokeEvents.Select(e => e.ActionId), testcase);
    }
}
