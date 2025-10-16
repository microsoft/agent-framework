// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Workflows.Declarative.Interpreter;
using Microsoft.Agents.AI.Workflows.Declarative.Kit;
using Microsoft.Agents.AI.Workflows.Declarative.PowerFx;
using Microsoft.Bot.ObjectModel;
using Microsoft.Extensions.AI;
using Moq;
using Xunit.Abstractions;
using Xunit.Sdk;

namespace Microsoft.Agents.AI.Workflows.Declarative.UnitTests;

/// <summary>
/// Tests execution of workflow created by <see cref="DeclarativeWorkflowBuilder"/>.
/// </summary>
public sealed class DeclarativeWorkflowTest(ITestOutputHelper output) : WorkflowTest(output)
{
    private List<WorkflowEvent> WorkflowEvents { get; } = [];

    private Dictionary<Type, int> WorkflowEventCounts { get; set; } = [];

    [Theory]
    [InlineData("BadEmpty.yaml")]
    [InlineData("BadId.yaml")]
    [InlineData("BadKind.yaml")]
    public async Task InvalidWorkflowAsync(string workflowFile)
    {
        await Assert.ThrowsAsync<DeclarativeModelException>(() => this.RunWorkflowAsync(workflowFile));
        this.AssertNotExecuted("end_all");
    }

    [Fact]
    public async Task LoopEachActionAsync()
    {
        await this.RunWorkflowAsync("LoopEach.yaml");
        this.AssertExecutionCount(expectedCount: 34);
        this.AssertExecuted("foreach_loop");
        this.AssertExecuted("set_variable_inner");
        this.AssertExecuted("send_activity_inner");
        this.AssertExecuted("end_all");
    }

    [Fact]
    public async Task LoopBreakActionAsync()
    {
        await this.RunWorkflowAsync("LoopBreak.yaml");
        this.AssertExecutionCount(expectedCount: 6);
        this.AssertExecuted("foreach_loop");
        this.AssertExecuted("break_loop_now");
        this.AssertExecuted("end_all");
        this.AssertNotExecuted("set_variable_inner");
        this.AssertNotExecuted("send_activity_inner");
    }

    [Fact]
    public async Task LoopContinueActionAsync()
    {
        await this.RunWorkflowAsync("LoopContinue.yaml");
        this.AssertExecutionCount(expectedCount: 22);
        this.AssertExecuted("foreach_loop");
        this.AssertExecuted("continue_loop_now");
        this.AssertExecuted("end_all");
        this.AssertNotExecuted("set_variable_inner");
        this.AssertNotExecuted("send_activity_inner");
    }

    [Fact]
    public async Task EndConversationActionAsync()
    {
        await this.RunWorkflowAsync("EndConversation.yaml");
        this.AssertExecutionCount(expectedCount: 1);
        this.AssertExecuted("end_all");
        this.AssertNotExecuted("sendActivity_1");
    }

    [Fact]
    public async Task GotoActionAsync()
    {
        await this.RunWorkflowAsync("Goto.yaml");
        this.AssertExecutionCount(expectedCount: 2);
        this.AssertExecuted("goto_end");
        this.AssertExecuted("end_all");
        this.AssertNotExecuted("sendActivity_1");
        this.AssertNotExecuted("sendActivity_2");
        this.AssertNotExecuted("sendActivity_3");
    }

    [Theory]
    [InlineData(12)]
    [InlineData(37)]
    public async Task ConditionActionAsync(int input)
    {
        await this.RunWorkflowAsync("Condition.yaml", input);
        this.AssertExecutionCount(expectedCount: 9);
        this.AssertExecuted("setVariable_test");
        this.AssertExecuted("conditionGroup_test");
        if (input % 2 == 0)
        {
            this.AssertExecuted("conditionItem_even", isScope: true);
            this.AssertExecuted("sendActivity_even");
            this.AssertNotExecuted("conditionItem_odd");
            this.AssertNotExecuted("sendActivity_odd");
            this.AssertMessage("EVEN");
        }
        else
        {
            this.AssertExecuted("conditionItem_odd", isScope: true);
            this.AssertExecuted("sendActivity_odd");
            this.AssertNotExecuted("conditionItem_even");
            this.AssertNotExecuted("sendActivity_even");
            this.AssertMessage("ODD");
        }
        this.AssertExecuted("end_all");
    }

    [Theory]
    [InlineData(12, 7)]
    [InlineData(37, 9)]
    public async Task ConditionActionWithElseAsync(int input, int expectedActions)
    {
        await this.RunWorkflowAsync("ConditionElse.yaml", input);
        this.AssertExecutionCount(expectedActions);
        this.AssertExecuted("setVariable_test");
        this.AssertExecuted("conditionGroup_test");
        if (input % 2 == 0)
        {
            this.AssertExecuted("sendActivity_else", isScope: true);
            this.AssertNotExecuted("conditionItem_odd");
            this.AssertNotExecuted("sendActivity_odd");
        }
        else
        {
            this.AssertExecuted("conditionItem_odd", isScope: true);
            this.AssertExecuted("sendActivity_odd");
            this.AssertNotExecuted("sendActivity_else");
        }
        this.AssertExecuted("end_all");
    }

    [Theory]
    [InlineData("EndConversation.yaml", 1, "end_all")]
    [InlineData("EndDialog.yaml", 1, "end_all")]
    [InlineData("EditTable.yaml", 2, "edit_var")]
    [InlineData("EditTableV2.yaml", 2, "edit_var")]
    [InlineData("ParseValue.yaml", 2, "parse_var")]
    [InlineData("SendActivity.yaml", 2, "activity_input")]
    [InlineData("SetVariable.yaml", 1, "set_var")]
    [InlineData("SetTextVariable.yaml", 1, "set_text")]
    [InlineData("ClearAllVariables.yaml", 1, "clear_all")]
    [InlineData("ResetVariable.yaml", 2, "clear_var")]
    [InlineData("MixedScopes.yaml", 2, "activity_input")]
    public async Task ExecuteActionAsync(string workflowFile, int expectedCount, string expectedId)
    {
        await this.RunWorkflowAsync(workflowFile);
        this.AssertExecutionCount(expectedCount);
        this.AssertExecuted(expectedId);
    }

    [Theory]
    [InlineData(typeof(ActivateExternalTrigger.Builder))]
    [InlineData(typeof(AdaptiveCardPrompt.Builder))]
    [InlineData(typeof(BeginDialog.Builder))]
    [InlineData(typeof(CSATQuestion.Builder))]
    [InlineData(typeof(CancelAllDialogs.Builder))]
    [InlineData(typeof(CancelDialog.Builder))]
    [InlineData(typeof(CreateSearchQuery.Builder))]
    [InlineData(typeof(DeleteActivity.Builder))]
    [InlineData(typeof(DisableTrigger.Builder))]
    [InlineData(typeof(DisconnectedNodeContainer.Builder))]
    [InlineData(typeof(EmitEvent.Builder))]
    [InlineData(typeof(GetActivityMembers.Builder))]
    [InlineData(typeof(GetConversationMembers.Builder))]
    [InlineData(typeof(HttpRequestAction.Builder))]
    [InlineData(typeof(InvokeAIBuilderModelAction.Builder))]
    [InlineData(typeof(InvokeConnectorAction.Builder))]
    [InlineData(typeof(InvokeCustomModelAction.Builder))]
    [InlineData(typeof(InvokeFlowAction.Builder))]
    [InlineData(typeof(InvokeSkillAction.Builder))]
    [InlineData(typeof(LogCustomTelemetryEvent.Builder))]
    [InlineData(typeof(OAuthInput.Builder))]
    [InlineData(typeof(RecognizeIntent.Builder))]
    [InlineData(typeof(RepeatDialog.Builder))]
    [InlineData(typeof(ReplaceDialog.Builder))]
    [InlineData(typeof(SearchAndSummarizeContent.Builder))]
    [InlineData(typeof(SearchAndSummarizeWithCustomModel.Builder))]
    [InlineData(typeof(SearchKnowledgeSources.Builder))]
    [InlineData(typeof(SignOutUser.Builder))]
    [InlineData(typeof(TransferConversation.Builder))]
    [InlineData(typeof(TransferConversationV2.Builder))]
    [InlineData(typeof(UnknownDialogAction.Builder))]
    [InlineData(typeof(UpdateActivity.Builder))]
    [InlineData(typeof(WaitForConnectorTrigger.Builder))]
    public void UnsupportedAction(Type type)
    {
        DialogAction.Builder? unsupportedAction = (DialogAction.Builder?)Activator.CreateInstance(type);
        Assert.NotNull(unsupportedAction);
        unsupportedAction.Id = "action_bad";
        AdaptiveDialog.Builder dialogBuilder =
            new()
            {
                BeginDialog =
                    new OnActivity.Builder()
                    {
                        Id = "anything",
                        Actions = [unsupportedAction]
                    }
            };
        AdaptiveDialog dialog = dialogBuilder.Build();

        WorkflowFormulaState state = new(RecalcEngineFactory.Create());
        Mock<WorkflowAgentProvider> mockAgentProvider = CreateMockProvider("1");
        DeclarativeWorkflowOptions options = new(mockAgentProvider.Object);
        WorkflowActionVisitor visitor = new(new DeclarativeWorkflowExecutor<string>(WorkflowActionVisitor.Steps.Root("anything"), options, state, (message) => DeclarativeWorkflowBuilder.DefaultTransform(message)), state, options);
        WorkflowElementWalker walker = new(visitor);
        walker.Visit(dialog);
        Assert.True(visitor.HasUnsupportedActions);
    }

    private void AssertExecutionCount(int expectedCount)
    {
        Assert.Equal(expectedCount + 2, this.WorkflowEventCounts[typeof(ExecutorInvokedEvent)]);
        Assert.Equal(expectedCount + 2, this.WorkflowEventCounts[typeof(ExecutorCompletedEvent)]);
    }

    private void AssertNotExecuted(string executorId)
    {
        Assert.DoesNotContain(this.WorkflowEvents.OfType<ExecutorInvokedEvent>(), e => e.ExecutorId == executorId);
        Assert.DoesNotContain(this.WorkflowEvents.OfType<ExecutorCompletedEvent>(), e => e.ExecutorId == executorId);
    }

    private void AssertExecuted(string executorId, bool isScope = false)
    {
        Assert.Contains(this.WorkflowEvents.OfType<ExecutorInvokedEvent>(), e => e.ExecutorId == executorId);
        Assert.Contains(this.WorkflowEvents.OfType<ExecutorCompletedEvent>(), e => e.ExecutorId == executorId);
        if (!isScope)
        {
            Assert.Contains(this.WorkflowEvents.OfType<DeclarativeActionInvokedEvent>(), e => e.ActionId == executorId);
            Assert.Contains(this.WorkflowEvents.OfType<DeclarativeActionCompletedEvent>(), e => e.ActionId == executorId);
        }
    }

    private void AssertMessage(string message) =>
        Assert.Contains(this.WorkflowEvents.OfType<MessageActivityEvent>(), e => string.Equals(e.Message.Trim(), message, StringComparison.Ordinal));

    private Task RunWorkflowAsync(string workflowPath) =>
        this.RunWorkflowAsync(workflowPath, "Test input message");

    private async Task RunWorkflowAsync<TInput>(string workflowPath, TInput workflowInput) where TInput : notnull
    {
        using StreamReader yamlReader = File.OpenText(Path.Combine("Workflows", workflowPath));
        Mock<WorkflowAgentProvider> mockAgentProvider = CreateMockProvider($"{workflowInput}");
        DeclarativeWorkflowOptions workflowContext = new(mockAgentProvider.Object) { LoggerFactory = this.Output };

        Workflow workflow = DeclarativeWorkflowBuilder.Build<TInput>(yamlReader, workflowContext);

        await using StreamingRun run = await InProcessExecution.StreamAsync(workflow, workflowInput);

        await foreach (WorkflowEvent workflowEvent in run.WatchStreamAsync())
        {
            this.WorkflowEvents.Add(workflowEvent);

            switch (workflowEvent)
            {
                case ExecutorInvokedEvent invokeEvent:
                    ActionExecutorResult? message = invokeEvent.Data as ActionExecutorResult;
                    this.Output.WriteLine($"EXEC: {invokeEvent.ExecutorId} << {message?.ExecutorId ?? "?"} [{message?.Result ?? "-"}]");
                    break;

                case DeclarativeActionInvokedEvent actionInvokeEvent:
                    this.Output.WriteLine($"ACTION ENTER: {actionInvokeEvent.ActionId}");
                    break;

                case DeclarativeActionCompletedEvent actionCompleteEvent:
                    this.Output.WriteLine($"ACTION EXIT: {actionCompleteEvent.ActionId}");
                    break;

                case MessageActivityEvent activityEvent:
                    this.Output.WriteLine($"ACTIVITY: {activityEvent.Message}");
                    break;

                case AgentRunResponseEvent messageEvent:
                    this.Output.WriteLine($"MESSAGE: {messageEvent.Response.Messages[0].Text.Trim()}");
                    break;

                case ExecutorFailedEvent failureEvent:
                    Console.WriteLine($"Executor failed [{failureEvent.ExecutorId}]: {failureEvent.Data?.Message ?? "Unknown"}");
                    break;

                case WorkflowErrorEvent errorEvent:
                    throw errorEvent.Data as Exception ?? new XunitException("Unexpected failure...");
            }
        }

        this.WorkflowEventCounts = this.WorkflowEvents.GroupBy(e => e.GetType()).ToDictionary(e => e.Key, e => e.Count());
    }

    private static Mock<WorkflowAgentProvider> CreateMockProvider(string input)
    {
        Mock<WorkflowAgentProvider> mockAgentProvider = new(MockBehavior.Strict);
        mockAgentProvider.Setup(provider => provider.CreateConversationAsync(It.IsAny<CancellationToken>())).Returns(() => Task.FromResult(Guid.NewGuid().ToString("N")));
        mockAgentProvider.Setup(provider => provider.CreateMessageAsync(It.IsAny<string>(), It.IsAny<ChatMessage>(), It.IsAny<CancellationToken>())).Returns(Task.FromResult(new ChatMessage(ChatRole.Assistant, input)));
        return mockAgentProvider;
    }
}
