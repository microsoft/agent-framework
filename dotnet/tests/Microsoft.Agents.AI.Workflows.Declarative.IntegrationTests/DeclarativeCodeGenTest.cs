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
public sealed class DeclarativeCodeGenTest(ITestOutputHelper output) : WorkflowTest(output)
{
    [Theory]
    [InlineData("CheckSystem.yaml", "CheckSystem.json")]
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
    public Task ValidateScenarioAsync(string workflowFileName, string testcaseFileName, bool externalConveration = false) =>
        this.RunWorkflowAsync(Path.Combine(GetRepoFolder(), "workflow-samples", workflowFileName), testcaseFileName, externalConveration);

    [Fact(Skip = "Needs template support")]
    public Task ValidateMultiTurnAsync() =>
        this.RunWorkflowAsync(Path.Combine(GetRepoFolder(), "workflow-samples", "HumanInLoop.yaml"), "HumanInLoop.json", useJsonCheckpoint: true);

    protected override async Task RunAndVerifyAsync<TInput>(Testcase testcase, string workflowPath, DeclarativeWorkflowOptions workflowOptions, TInput input, bool useJsonCheckpoint)
    {
        const string WorkflowNamespace = "Test.WorkflowProviders";
        const string WorkflowPrefix = "Test";

        string workflowProviderCode = DeclarativeWorkflowBuilder.Eject(workflowPath, DeclarativeWorkflowLanguage.CSharp, WorkflowNamespace, WorkflowPrefix);
        try
        {
            WorkflowHarness harness = await WorkflowHarness.GenerateCodeAsync(
                runId: Path.GetFileNameWithoutExtension(workflowPath),
                workflowProviderCode,
                workflowProviderName: $"{WorkflowPrefix}WorkflowProvider",
                WorkflowNamespace,
                workflowOptions,
                input);

            WorkflowEvents workflowEvents = await harness.RunTestcaseAsync(testcase, input, useJsonCheckpoint).ConfigureAwait(false);

            // Verify no action events are present
            Assert.Empty(workflowEvents.ActionInvokeEvents);
            Assert.Empty(workflowEvents.ActionCompleteEvents);
            // Verify the associated conversations
            AssertWorkflow.Conversation(workflowEvents.ConversationEvents, testcase);
            // Verify executor events
            AssertWorkflow.EventCounts(workflowEvents.ExecutorInvokeEvents.Count - 2, testcase);
            AssertWorkflow.EventCounts(workflowEvents.ExecutorCompleteEvents.Count - 2, testcase);
            // Verify action sequences
            AssertWorkflow.EventSequence(workflowEvents.ExecutorInvokeEvents.Select(e => e.ExecutorId), testcase);
        }
        finally
        {
            this.Output.WriteLine($"CODE:\n{workflowProviderCode}");
        }
    }
}
