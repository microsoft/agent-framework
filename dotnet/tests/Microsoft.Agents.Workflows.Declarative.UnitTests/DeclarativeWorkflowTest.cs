// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Immutable;
using System.IO;
using System.Linq;
using System.Threading.Tasks;
using Microsoft.Agents.Workflows.Declarative.Interpreter;
using Microsoft.Agents.Workflows.Declarative.PowerFx;
using Microsoft.Agents.Workflows.Reflection;
using Microsoft.Bot.ObjectModel;
using Microsoft.Extensions.Logging.Abstractions;
using Xunit.Abstractions;

namespace Microsoft.Agents.Workflows.Declarative.UnitTests;

/// <summary>
/// Tests exeuction of workflow created by <see cref="DeclarativeWorkflowBuilder"/>.
/// </summary>
public sealed class DeclarativeWorkflowTest(ITestOutputHelper output) : WorkflowTest(output)
{
    private ImmutableList<WorkflowEvent> WorkflowEvents { get; set; } = ImmutableList<WorkflowEvent>.Empty;

    private ImmutableDictionary<Type, int> WorkflowEventCounts { get; set; } = ImmutableDictionary<Type, int>.Empty;

    [Fact]
    public async Task SingleAction()
    {
        await this.RunWorkflow("Single.yaml");
        this.AssertExecutionCount(expectedCount: 1);
        this.AssertExecuted("end_all");
    }

    [Fact]
    public async Task LoopEachAction()
    {
        await this.RunWorkflow("LoopEach.yaml");
        this.AssertExecutionCount(expectedCount: 35);
        this.AssertExecuted("foreach_loop");
        this.AssertExecuted("end_all");
    }

    [Fact]
    public async Task LoopBreakAction()
    {
        await this.RunWorkflow("LoopBreak.yaml");
        this.AssertExecutionCount(expectedCount: 7);
        this.AssertExecuted("foreach_loop");
        this.AssertExecuted("breakLoop_now");
        this.AssertExecuted("end_all");
        this.AssertNotExecuted("setVariable_loop");
        this.AssertNotExecuted("sendActivity_loop");
    }

    [Fact]
    public async Task LoopContinueAction()
    {
        await this.RunWorkflow("LoopContinue.yaml");
        this.AssertExecutionCount(expectedCount: 23);
        this.AssertExecuted("foreach_loop");
        this.AssertExecuted("continueLoop_now");
        this.AssertExecuted("end_all");
        this.AssertNotExecuted("setVariable_loop");
        this.AssertNotExecuted("sendActivity_loop");
    }

    [Fact]
    public async Task GotoAction()
    {
        await this.RunWorkflow("Goto.yaml");
        this.AssertExecutionCount(expectedCount: 2);
        this.AssertExecuted("goto_end");
        this.AssertExecuted("end_all");
        this.AssertNotExecuted("sendActivity_1");
        this.AssertNotExecuted("sendActivity_2");
        this.AssertNotExecuted("sendActivity_3");
    }

    [Fact]
    public async Task ConditionAction()
    {
        await this.RunWorkflow("Condition.yaml");
        this.AssertExecutionCount(expectedCount: 16);
        this.AssertExecuted("setVariable_test");
        this.AssertExecuted("conditionGroup_test");
        this.AssertExecuted("conditionItem_even");
        this.AssertExecuted("sendActivity_even");
        this.AssertExecuted("end_all");
        this.AssertNotExecuted("conditionItem_odd");
        this.AssertNotExecuted("sendActivity_odd");
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
    [InlineData(typeof(EndDialog.Builder))]
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
    [InlineData(typeof(Question.Builder))]
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
    public async Task UnsupportedAction(Type type)
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
                        Id = "workflow",
                        Actions = [unsupportedAction]
                    }
            };

        WorkflowScopes scopes = new();
        DeclarativeWorkflowContext workflowContext =
            new()
            {
                LoggerFactory = NullLoggerFactory.Instance,
                ActivityChannel = this.Output,
            };
        WorkflowActionVisitor visitor = new(new RootExecutor(), workflowContext, scopes);
        WorkflowElementWalker walker = new(dialogBuilder.Build(), visitor);
        Assert.True(visitor.HasUnsupportedActions);
    }

    private void AssertExecutionCount(int expectedCount)
    {
        Assert.Equal(expectedCount + 2, this.WorkflowEventCounts[typeof(ExecutorInvokeEvent)]);
        Assert.Equal(expectedCount + 2, this.WorkflowEventCounts[typeof(ExecutorCompleteEvent)]);
    }

    private void AssertNotExecuted(string executorId)
    {
        Assert.DoesNotContain(this.WorkflowEvents.OfType<ExecutorInvokeEvent>(), e => e.ExecutorId == executorId);
        Assert.DoesNotContain(this.WorkflowEvents.OfType<ExecutorCompleteEvent>(), e => e.ExecutorId == executorId);
    }

    private void AssertExecuted(string executorId)
    {
        Assert.Contains(this.WorkflowEvents.OfType<ExecutorInvokeEvent>(), e => e.ExecutorId == executorId);
        Assert.Contains(this.WorkflowEvents.OfType<ExecutorCompleteEvent>(), e => e.ExecutorId == executorId);
    }

    private async Task RunWorkflow(string workflowPath)
    {
        using StreamReader yamlReader = File.OpenText(Path.Combine("Workflows", workflowPath));
        DeclarativeWorkflowContext workflowContext =
            new()
            {
                LoggerFactory = NullLoggerFactory.Instance,
                ActivityChannel = this.Output,
            };

        Workflow<string> workflow = DeclarativeWorkflowBuilder.Build(yamlReader, workflowContext);

        StreamingRun run = await InProcessExecution.StreamAsync(workflow, "<placeholder>");

        this.WorkflowEvents = run.WatchStreamAsync().ToEnumerable().ToImmutableList();
        this.WorkflowEventCounts = this.WorkflowEvents.GroupBy(e => e.GetType()).ToImmutableDictionary(e => e.Key, e => e.Count());
    }

    private sealed class RootExecutor() :
        ReflectingExecutor<RootExecutor>("root_workflow"),
        IMessageHandler<string>
    {
        public async ValueTask HandleAsync(string message, IWorkflowContext context)
        {
            await context.SendMessageAsync($"{this.Id}: {DateTime.UtcNow.ToShortTimeString()}").ConfigureAwait(false);
        }
    }
}
