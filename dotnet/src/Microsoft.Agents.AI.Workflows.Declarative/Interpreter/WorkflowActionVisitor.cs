// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Diagnostics;
using System.Linq;
using Microsoft.Agents.AI.Workflows.Declarative.Events;
using Microsoft.Agents.AI.Workflows.Declarative.Extensions;
using Microsoft.Agents.AI.Workflows.Declarative.Kit;
using Microsoft.Agents.AI.Workflows.Declarative.ObjectModel;
using Microsoft.Agents.AI.Workflows.Declarative.PowerFx;
using Microsoft.Bot.ObjectModel;

namespace Microsoft.Agents.AI.Workflows.Declarative.Interpreter;

internal sealed class WorkflowActionVisitor : DialogActionVisitor
{
    private const string DefaultWorkflowId = "workflow";

    internal static class Steps
    {
        public static string Root(AdaptiveDialog action) => $"{action.BeginDialog?.Id.Value ?? DefaultWorkflowId}_{nameof(Root)}";

        public static string Root(string? actionId = null) => $"{actionId ?? DefaultWorkflowId}_{nameof(Root)}";

        public static string Post(string actionId) => $"{actionId}_{nameof(Post)}";

        public static string Restart(string actionId) => $"{actionId}_{nameof(Restart)}";
    }

    private readonly Executor _rootAction;
    private readonly WorkflowModel<Func<object?, bool>> _workflowModel;
    private readonly DeclarativeWorkflowOptions _workflowOptions;
    private readonly WorkflowFormulaState _workflowState;

    public WorkflowActionVisitor(
        Executor rootAction,
        WorkflowFormulaState state,
        DeclarativeWorkflowOptions options)
    {
        this._rootAction = rootAction;
        this._workflowModel = new WorkflowModel<Func<object?, bool>>((IModeledAction)rootAction);
        this._workflowOptions = options;
        this._workflowState = state;
    }

    public bool HasUnsupportedActions { get; private set; }

    public Workflow Complete()
    {
        WorkflowModelBuilder builder = new(this._rootAction);

        this._workflowModel.Build(builder);

        // Build final workflow
        return builder.WorkflowBuilder.Build();
    }

    protected override void Visit(ActionScope item)
    {
        this.Trace(item);

        string parentId = GetParentId(item);

        // Handle case where root element is its own parent
        if (item.Id.Equals(parentId))
        {
            parentId = Steps.Root(parentId);
        }

        this.ContinueWith(new DelegateActionExecutor(item.Id.Value, this._workflowState), parentId, condition: null, CompletionHandler);

        // Complete the action scope.
        void CompletionHandler()
        {
            // No completion for root scope
            if (this._workflowModel.GetDepth(item.Id.Value) > 1)
            {
                DelegateAction<ActionExecutorResult>? action = null;
                ConditionGroupExecutor? conditionGroup = this._workflowModel.LocateParent<ConditionGroupExecutor>(parentId);
                if (conditionGroup is not null)
                {
                    action = conditionGroup.DoneAsync;
                }

                // Define post action for this scope
                string completionId = this.ContinuationFor(item.Id.Value, action);
                this._workflowModel.AddLinkFromPeer(item.Id.Value, completionId);
                // Transition to post action of parent scope
                this._workflowModel.AddLink(completionId, Steps.Post(parentId));
            }
        }
    }

    public override void VisitConditionItem(ConditionItem item)
    {
        this.Trace(item);

        string parentId = GetParentId(item);
        ConditionGroupExecutor? conditionGroup = this._workflowModel.LocateParent<ConditionGroupExecutor>(parentId);
        if (conditionGroup is not null)
        {
            string stepId = ConditionGroupExecutor.Steps.Item(conditionGroup.Model, item);
            this._workflowModel.AddNode(new DelegateActionExecutor(stepId, this._workflowState), parentId, CompletionHandler);

            base.VisitConditionItem(item);

            // Complete the condition item.
            void CompletionHandler()
            {
                string completionId = this.ContinuationFor(stepId, conditionGroup.DoneAsync); // End items
                this._workflowModel.AddLink(completionId, Steps.Post(conditionGroup.Id)); // Merge with parent scope

                // Merge link when no action group is defined
                if (!item.Actions.Any())
                {
                    this._workflowModel.AddLink(stepId, completionId);
                }
            }
        }
    }

    protected override void Visit(ConditionGroup item)
    {
        this.Trace(item);

        ConditionGroupExecutor action = new(item, this._workflowState);
        this.ContinueWith(action);
        this.ContinuationFor(action.Id, action.ParentId);

        string? lastConditionItemId = null;
        foreach (ConditionItem conditionItem in item.Conditions)
        {
            // Create conditional link for conditional action
            lastConditionItemId = ConditionGroupExecutor.Steps.Item(item, conditionItem);
            this._workflowModel.AddLink(action.Id, lastConditionItemId, (result) => action.IsMatch(conditionItem, result));

            conditionItem.Accept(this);
        }

        if (item.ElseActions?.Actions.Length > 0)
        {
            if (lastConditionItemId is not null)
            {
                // Create clean start for else action from prior conditions
                this.RestartAfter(lastConditionItemId, action.Id);
            }

            // Create conditional link for else action
            string stepId = ConditionGroupExecutor.Steps.Else(item);
            this._workflowModel.AddLink(action.Id, stepId, action.IsElse);
        }
    }

    protected override void Visit(GotoAction item)
    {
        this.Trace(item);

        // Represent action with default executor
        DefaultActionExecutor action = new(item, this._workflowState);
        this.ContinueWith(action);
        // Transition to target action
        this._workflowModel.AddLink(action.Id, item.ActionId.Value);
        // Define a clean-start to ensure "goto" is not a source for any edge
        this.RestartAfter(action.Id, action.ParentId);
    }

    protected override void Visit(Foreach item)
    {
        this.Trace(item);

        // Entry point for loop
        ForeachExecutor action = new(item, this._workflowState);
        string loopId = ForeachExecutor.Steps.Next(action.Id);
        this.ContinueWith(action, condition: null, CompletionHandler);
        // Transition to select the next item
        this.ContinueWith(new DelegateActionExecutor(loopId, this._workflowState, action.TakeNextAsync), action.Id);

        // Transition to post action if no more items
        string continuationId = this.ContinuationFor(action.Id, action.ParentId);
        this._workflowModel.AddLink(loopId, continuationId, (_) => !action.HasValue);

        // Transition to start of inner actions if there is a current item
        string startId = ForeachExecutor.Steps.Start(action.Id);
        this._workflowModel.AddNode(new DelegateActionExecutor(startId, this._workflowState), action.Id);
        this._workflowModel.AddLink(loopId, startId, (_) => action.HasValue);

        void CompletionHandler()
        {
            // Transition to end of inner actions
            string endActionsId = ForeachExecutor.Steps.End(action.Id);
            this.ContinueWith(new DelegateActionExecutor(endActionsId, this._workflowState, action.ResetAsync), action.Id);
            // Transition to select the next item
            this._workflowModel.AddLink(endActionsId, loopId);
        }
    }

    protected override void Visit(BreakLoop item)
    {
        this.Trace(item);

        // Locate the nearest "Foreach" loop that contains this action
        ForeachExecutor? loopAction = this._workflowModel.LocateParent<ForeachExecutor>(item.GetParentId());
        // Skip action if its not contained a loop
        if (loopAction is not null)
        {
            // Represent action with default executor
            DefaultActionExecutor action = new(item, this._workflowState);
            this.ContinueWith(action);
            // Transition to post action
            this._workflowModel.AddLink(action.Id, Steps.Post(loopAction.Id));
            // Define a clean-start to ensure "break" is not a source for any edge
            this.RestartAfter(action.Id, action.ParentId);
        }
    }

    protected override void Visit(ContinueLoop item)
    {
        this.Trace(item);

        // Locate the nearest "Foreach" loop that contains this action
        ForeachExecutor? loopAction = this._workflowModel.LocateParent<ForeachExecutor>(item.GetParentId());
        // Skip action if its not contained a loop
        if (loopAction is not null)
        {
            // Represent action with default executor
            DefaultActionExecutor action = new(item, this._workflowState);
            this.ContinueWith(action);
            // Transition to select the next item
            this._workflowModel.AddLink(action.Id, ForeachExecutor.Steps.Next(loopAction.Id));
            // Define a clean-start to ensure "continue" is not a source for any edge
            this.RestartAfter(action.Id, action.ParentId);
        }
    }

    protected override void Visit(Question item)
    {
        this.Trace(item);

        string parentId = GetParentId(item);
        string actionId = item.GetId();
        string postId = Steps.Post(actionId);

        // Entry point for question
        QuestionExecutor action = new(item, this._workflowState);
        this.ContinueWith(action);
        // Transition to post action if complete
        this._workflowModel.AddLink(actionId, postId, QuestionExecutor.IsComplete);

        // Perpare for input request if not complete
        string prepareId = QuestionExecutor.Steps.Prepare(actionId);
        this.ContinueWith(new DelegateActionExecutor(prepareId, this._workflowState, action.PrepareResponseAsync, emitResult: false), parentId, message => !QuestionExecutor.IsComplete(message));

        // Define input action
        string inputId = QuestionExecutor.Steps.Input(actionId);
        RequestPortAction inputPort = new(RequestPort.Create<InputRequest, InputResponse>(inputId));
        this._workflowModel.AddNode(inputPort, parentId);
        this._workflowModel.AddLinkFromPeer(parentId, inputId);

        // Capture input response
        string captureId = QuestionExecutor.Steps.Capture(actionId);
        this.ContinueWith(new DelegateActionExecutor<InputResponse>(captureId, this._workflowState, action.CaptureResponseAsync, emitResult: false), parentId);

        // Transition to post action if complete
        this.ContinueWith(new DelegateActionExecutor(postId, this._workflowState, action.CompleteAsync), parentId, QuestionExecutor.IsComplete);
        // Transition to prepare action if not complete
        this._workflowModel.AddLink(captureId, prepareId, message => !QuestionExecutor.IsComplete(message));
    }

    protected override void Visit(EndDialog item)
    {
        this.Trace(item);

        // Represent action with default executor
        DefaultActionExecutor action = new(item, this._workflowState);
        this.ContinueWith(action);
        // Define a clean-start to ensure "end" is not a source for any edge
        this.RestartAfter(item.Id.Value, action.ParentId);
    }

    protected override void Visit(EndConversation item)
    {
        this.Trace(item);

        // Represent action with default executor
        DefaultActionExecutor action = new(item, this._workflowState);
        this.ContinueWith(action);
        // Define a clean-start to ensure "end" is not a source for any edge
        this.RestartAfter(action.Id, action.ParentId);
    }

    protected override void Visit(CreateConversation item)
    {
        this.Trace(item);

        this.ContinueWith(new CreateConversationExecutor(item, this._workflowOptions.AgentProvider, this._workflowState));
    }

    protected override void Visit(AddConversationMessage item)
    {
        this.Trace(item);

        this.ContinueWith(new AddConversationMessageExecutor(item, this._workflowOptions.AgentProvider, this._workflowState));
    }

    protected override void Visit(CopyConversationMessages item)
    {
        this.Trace(item);

        this.ContinueWith(new CopyConversationMessagesExecutor(item, this._workflowOptions.AgentProvider, this._workflowState));
    }

    protected override void Visit(InvokeAzureAgent item)
    {
        this.Trace(item);

        this.ContinueWith(new InvokeAzureAgentExecutor(item, this._workflowOptions.AgentProvider, this._workflowState));
    }

    protected override void Visit(RetrieveConversationMessage item)
    {
        this.Trace(item);

        this.ContinueWith(new RetrieveConversationMessageExecutor(item, this._workflowOptions.AgentProvider, this._workflowState));
    }

    protected override void Visit(RetrieveConversationMessages item)
    {
        this.Trace(item);

        this.ContinueWith(new RetrieveConversationMessagesExecutor(item, this._workflowOptions.AgentProvider, this._workflowState));
    }

    protected override void Visit(SetVariable item)
    {
        this.Trace(item);

        this.ContinueWith(new SetVariableExecutor(item, this._workflowState));
    }

    protected override void Visit(SetMultipleVariables item)
    {
        this.Trace(item);

        this.ContinueWith(new SetMultipleVariablesExecutor(item, this._workflowState));
    }

    protected override void Visit(SetTextVariable item)
    {
        this.Trace(item);

        this.ContinueWith(new SetTextVariableExecutor(item, this._workflowState));
    }

    protected override void Visit(ClearAllVariables item)
    {
        this.Trace(item);

        this.ContinueWith(new ClearAllVariablesExecutor(item, this._workflowState));
    }

    protected override void Visit(ResetVariable item)
    {
        this.Trace(item);

        this.ContinueWith(new ResetVariableExecutor(item, this._workflowState));
    }

    protected override void Visit(EditTable item)
    {
        this.Trace(item);

        this.ContinueWith(new EditTableExecutor(item, this._workflowState));
    }

    protected override void Visit(EditTableV2 item)
    {
        this.Trace(item);

        this.ContinueWith(new EditTableV2Executor(item, this._workflowState));
    }

    protected override void Visit(ParseValue item)
    {
        this.Trace(item);

        this.ContinueWith(new ParseValueExecutor(item, this._workflowState));
    }

    protected override void Visit(SendActivity item)
    {
        this.Trace(item);

        this.ContinueWith(new SendActivityExecutor(item, this._workflowState));
    }

    #region Not supported

    protected override void Visit(AnswerQuestionWithAI item) => this.NotSupported(item);

    protected override void Visit(DeleteActivity item) => this.NotSupported(item);

    protected override void Visit(GetActivityMembers item) => this.NotSupported(item);

    protected override void Visit(UpdateActivity item) => this.NotSupported(item);

    protected override void Visit(ActivateExternalTrigger item) => this.NotSupported(item);

    protected override void Visit(DisableTrigger item) => this.NotSupported(item);

    protected override void Visit(WaitForConnectorTrigger item) => this.NotSupported(item);

    protected override void Visit(InvokeConnectorAction item) => this.NotSupported(item);

    protected override void Visit(InvokeCustomModelAction item) => this.NotSupported(item);

    protected override void Visit(InvokeFlowAction item) => this.NotSupported(item);

    protected override void Visit(InvokeAIBuilderModelAction item) => this.NotSupported(item);

    protected override void Visit(InvokeSkillAction item) => this.NotSupported(item);

    protected override void Visit(AdaptiveCardPrompt item) => this.NotSupported(item);

    protected override void Visit(CSATQuestion item) => this.NotSupported(item);

    protected override void Visit(OAuthInput item) => this.NotSupported(item);

    protected override void Visit(BeginDialog item) => this.NotSupported(item);

    protected override void Visit(UnknownDialogAction item) => this.NotSupported(item);

    protected override void Visit(RepeatDialog item) => this.NotSupported(item);

    protected override void Visit(ReplaceDialog item) => this.NotSupported(item);

    protected override void Visit(CancelAllDialogs item) => this.NotSupported(item);

    protected override void Visit(CancelDialog item) => this.NotSupported(item);

    protected override void Visit(EmitEvent item) => this.NotSupported(item);

    protected override void Visit(GetConversationMembers item) => this.NotSupported(item);

    protected override void Visit(HttpRequestAction item) => this.NotSupported(item);

    protected override void Visit(RecognizeIntent item) => this.NotSupported(item);

    protected override void Visit(TransferConversation item) => this.NotSupported(item);

    protected override void Visit(TransferConversationV2 item) => this.NotSupported(item);

    protected override void Visit(SignOutUser item) => this.NotSupported(item);

    protected override void Visit(LogCustomTelemetryEvent item) => this.NotSupported(item);

    protected override void Visit(DisconnectedNodeContainer item) => this.NotSupported(item);

    protected override void Visit(CreateSearchQuery item) => this.NotSupported(item);

    protected override void Visit(SearchKnowledgeSources item) => this.NotSupported(item);

    protected override void Visit(SearchAndSummarizeWithCustomModel item) => this.NotSupported(item);

    protected override void Visit(SearchAndSummarizeContent item) => this.NotSupported(item);

    #endregion

    private void ContinueWith(
        DeclarativeActionExecutor executor,
        Func<object?, bool>? condition = null,
        Action? completionHandler = null)
    {
        executor.Logger = this._workflowOptions.LoggerFactory.CreateLogger(executor.Id);
        this.ContinueWith(executor, executor.ParentId, condition, completionHandler);
    }

    private void ContinueWith(
        IModeledAction action,
        string parentId,
        Func<object?, bool>? condition = null,
        Action? completionHandler = null)
    {
        this._workflowModel.AddNode(action, parentId, completionHandler);
        this._workflowModel.AddLinkFromPeer(parentId, action.Id, condition);
    }

    private string ContinuationFor(string parentId, DelegateAction<ActionExecutorResult>? stepAction = null) => this.ContinuationFor(parentId, parentId, stepAction);

    private string ContinuationFor(string actionId, string parentId, DelegateAction<ActionExecutorResult>? stepAction = null)
    {
        actionId = Steps.Post(actionId);
        this._workflowModel.AddNode(new DelegateActionExecutor(actionId, this._workflowState, stepAction), parentId);
        return actionId;
    }

    private void RestartAfter(string actionId, string parentId) =>
        this._workflowModel.AddNode(new DelegateActionExecutor(Steps.Restart(actionId), this._workflowState), parentId);

    private static string GetParentId(BotElement item) =>
        item.GetParentId() ??
        throw new DeclarativeModelException($"Missing parent ID for action element: {item.GetId()} [{item.GetType().Name}].");

    private void NotSupported(DialogAction item)
    {
        Debug.WriteLine($"> UNKNOWN: {new string('\t', this._workflowModel.GetDepth(item.GetParentId()))}{FormatItem(item)} => {FormatParent(item)}");
        this.HasUnsupportedActions = true;
    }

    private void Trace(BotElement item) =>
        Debug.WriteLine($"> VISIT: {new string('\t', this._workflowModel.GetDepth(item.GetParentId()))}{FormatItem(item)} => {FormatParent(item)}");

    private void Trace(DialogAction item)
    {
        string? parentId = item.GetParentId();
        if (item.Id.Equals(parentId ?? string.Empty))
        {
            parentId = Steps.Root(parentId);
        }

        Debug.WriteLine($"> VISIT: {new string('\t', this._workflowModel.GetDepth(parentId))}{FormatItem(item)} => {FormatParent(item)}");
    }

    private static string FormatItem(BotElement element) => $"{element.GetType().Name} ({element.GetId()})";

    private static string FormatParent(BotElement element) =>
        element.Parent is null ?
        throw new DeclarativeModelException($"Undefined parent for {element.GetType().Name} that is member of {element.GetId()}.") :
        $"{element.Parent.GetType().Name} ({element.GetParentId()})";
}
