// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Diagnostics;
using System.Linq;
using Microsoft.Agents.Workflows.Declarative.Extensions;
using Microsoft.Agents.Workflows.Declarative.ObjectModel;
using Microsoft.Bot.ObjectModel;

namespace Microsoft.Agents.Workflows.Declarative.Interpreter;

internal sealed class WorkflowActionVisitor : DialogActionVisitor
{
    private readonly WorkflowBuilder _workflowBuilder;
    private readonly DeclarativeWorkflowModel _workflowModel;
    private readonly DeclarativeWorkflowOptions _workflowOptions;
    private readonly DeclarativeWorkflowState _workflowState;

    public WorkflowActionVisitor(
        Executor rootAction,
        DeclarativeWorkflowState state,
        DeclarativeWorkflowOptions options)
    {
        this._workflowBuilder = new WorkflowBuilder(rootAction);
        this._workflowModel = new DeclarativeWorkflowModel(rootAction);
        this._workflowOptions = options;
        this._workflowState = state;
    }

    public bool HasUnsupportedActions { get; private set; }

    public Workflow<TInput> Complete<TInput>()
    {
        // Process the cached links
        this._workflowModel.ConnectNodes(this._workflowBuilder);

        // Build final workflow
        return this._workflowBuilder.Build<TInput>();
    }

    protected override void Visit(ActionScope item)
    {
        this.Trace(item);

        string parentId = GetParentId(item);

        // Handle case where root element is its own parent
        if (item.Id.Equals(parentId))
        {
            parentId = RootId(parentId);
        }

        this.ContinueWith(this.CreateStep(item.Id.Value), parentId, condition: null, CompletionHandler);

        // Complete the action scope.
        void CompletionHandler()
        {
            if (this._workflowModel.GetDepth(item.Id.Value) > 1)
            {
                string completionId = this.ContinuationFor(item.Id.Value); // End scope
                this._workflowModel.AddLinkFromPeer(item.Id.Value, completionId); // Connect with final action
                this._workflowModel.AddLink(completionId, PostId(parentId)); // Merge with parent scope
            }
        }
    }

    public override void VisitConditionItem(ConditionItem item)
    {
        this.Trace(item);

        ConditionGroupExecutor? conditionGroup = this._workflowModel.LocateParent<ConditionGroupExecutor>(item.GetParentId());
        if (conditionGroup is not null)
        {
            string stepId = ConditionGroupExecutor.Steps.Item(conditionGroup.Model, item);
            string parentId = GetParentId(item);
            this._workflowModel.AddNode(this.CreateStep(stepId), parentId, CompletionHandler);

            base.VisitConditionItem(item);

            // Complete the condition item.
            void CompletionHandler()
            {
                string completionId = this.ContinuationFor(stepId); // End items
                this._workflowModel.AddLink(completionId, PostId(conditionGroup.Id)); // Merge with parent scope

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
            this._workflowModel.AddLink(action.Id, stepId, (result) => action.IsElse(result));
        }
    }

    protected override void Visit(GotoAction item)
    {
        this.Trace(item);

        string parentId = GetParentId(item);
        this.ContinueWith(this.CreateStep(item.Id.Value), parentId);
        this._workflowModel.AddLink(item.Id.Value, item.ActionId.Value);
        this.RestartAfter(item.Id.Value, parentId);
    }

    protected override void Visit(Foreach item)
    {
        this.Trace(item);

        ForeachExecutor action = new(item, this._workflowState);
        string loopId = ForeachExecutor.Steps.Next(action.Id);
        this.ContinueWith(action, condition: null, CompletionHandler); // Foreach
        this.ContinueWith(this.CreateStep(loopId, action.TakeNextAsync), action.Id); // Loop Increment
        string continuationId = this.ContinuationFor(action.Id, action.ParentId); // Action continuation
        this._workflowModel.AddLink(loopId, continuationId, (_) => !action.HasValue);
        DelegateActionExecutor startAction = this.CreateStep(ForeachExecutor.Steps.Start(action.Id)); // Action start
        this._workflowModel.AddNode(startAction, action.Id);
        this._workflowModel.AddLink(loopId, startAction.Id, (_) => action.HasValue);

        void CompletionHandler()
        {
            string endActionsId = ForeachExecutor.Steps.End(action.Id); // Loop continuation
            this.ContinueWith(this.CreateStep(endActionsId, action.ResetAsync), action.Id);
            this._workflowModel.AddLink(endActionsId, loopId);
        }
    }

    protected override void Visit(BreakLoop item)
    {
        this.Trace(item);

        ForeachExecutor? loopExecutor = this._workflowModel.LocateParent<ForeachExecutor>(item.GetParentId());
        if (loopExecutor is not null)
        {
            string parentId = GetParentId(item);
            this.ContinueWith(this.CreateStep(item.Id.Value), parentId);
            this._workflowModel.AddLink(item.Id.Value, PostId(loopExecutor.Id));
            this.RestartAfter(item.Id.Value, parentId);
        }
    }

    protected override void Visit(ContinueLoop item)
    {
        this.Trace(item);

        ForeachExecutor? loopExecutor = this._workflowModel.LocateParent<ForeachExecutor>(item.GetParentId());
        if (loopExecutor is not null)
        {
            string parentId = GetParentId(item);
            this.ContinueWith(this.CreateStep(item.Id.Value), parentId);
            this._workflowModel.AddLink(item.Id.Value, ForeachExecutor.Steps.Next(loopExecutor.Id));
            this.RestartAfter(item.Id.Value, parentId);
        }
    }

    protected override void Visit(EndConversation item)
    {
        this.Trace(item);

        string parentId = GetParentId(item);
        this.ContinueWith(this.CreateStep(item.Id.Value), parentId);
        this.RestartAfter(item.Id.Value, parentId);
    }

    protected override void Visit(AnswerQuestionWithAI item)
    {
        this.Trace(item);

        this.ContinueWith(new AnswerQuestionWithAIExecutor(item, this._workflowOptions.AgentProvider, this._workflowState));
    }

    protected override void Visit(SetVariable item)
    {
        this.Trace(item);

        this.ContinueWith(new SetVariableExecutor(item, this._workflowState));
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

    protected override void Visit(DeleteActivity item)
    {
        this.NotSupported(item);
    }

    protected override void Visit(GetActivityMembers item)
    {
        this.NotSupported(item);
    }

    protected override void Visit(UpdateActivity item)
    {
        this.NotSupported(item);
    }

    protected override void Visit(ActivateExternalTrigger item)
    {
        this.NotSupported(item);
    }

    protected override void Visit(DisableTrigger item)
    {
        this.NotSupported(item);
    }

    protected override void Visit(WaitForConnectorTrigger item)
    {
        this.NotSupported(item);
    }

    protected override void Visit(InvokeConnectorAction item)
    {
        this.NotSupported(item);
    }

    protected override void Visit(InvokeCustomModelAction item)
    {
        this.NotSupported(item);
    }

    protected override void Visit(InvokeFlowAction item)
    {
        this.NotSupported(item);
    }

    protected override void Visit(InvokeAIBuilderModelAction item)
    {
        this.NotSupported(item);
    }

    protected override void Visit(InvokeSkillAction item)
    {
        this.NotSupported(item);
    }

    protected override void Visit(AdaptiveCardPrompt item)
    {
        this.NotSupported(item);
    }

    protected override void Visit(Question item)
    {
        this.NotSupported(item);
    }

    protected override void Visit(CSATQuestion item)
    {
        this.NotSupported(item);
    }

    protected override void Visit(OAuthInput item)
    {
        this.NotSupported(item);
    }

    protected override void Visit(BeginDialog item)
    {
        this.NotSupported(item);
    }

    protected override void Visit(UnknownDialogAction item)
    {
        this.NotSupported(item);
    }

    protected override void Visit(EndDialog item)
    {
        this.NotSupported(item);
    }

    protected override void Visit(RepeatDialog item)
    {
        this.NotSupported(item);
    }

    protected override void Visit(ReplaceDialog item)
    {
        this.NotSupported(item);
    }

    protected override void Visit(CancelAllDialogs item)
    {
        this.NotSupported(item);
    }

    protected override void Visit(CancelDialog item)
    {
        this.NotSupported(item);
    }

    protected override void Visit(EmitEvent item)
    {
        this.NotSupported(item);
    }

    protected override void Visit(GetConversationMembers item)
    {
        this.NotSupported(item);
    }

    protected override void Visit(HttpRequestAction item)
    {
        this.NotSupported(item);
    }

    protected override void Visit(RecognizeIntent item)
    {
        this.NotSupported(item);
    }

    protected override void Visit(TransferConversation item)
    {
        this.NotSupported(item);
    }

    protected override void Visit(TransferConversationV2 item)
    {
        this.NotSupported(item);
    }

    protected override void Visit(SignOutUser item)
    {
        this.NotSupported(item);
    }

    protected override void Visit(LogCustomTelemetryEvent item)
    {
        this.NotSupported(item);
    }

    protected override void Visit(DisconnectedNodeContainer item)
    {
        this.NotSupported(item);
    }

    protected override void Visit(CreateSearchQuery item)
    {
        this.NotSupported(item);
    }

    protected override void Visit(SearchKnowledgeSources item)
    {
        this.NotSupported(item);
    }

    protected override void Visit(SearchAndSummarizeWithCustomModel item)
    {
        this.NotSupported(item);
    }

    protected override void Visit(SearchAndSummarizeContent item)
    {
        this.NotSupported(item);
    }

    #endregion

    private void ContinueWith(
        WorkflowActionExecutor executor,
        Func<object?, bool>? condition = null,
        Action? completionHandler = null)
    {
        executor.Logger = this._workflowOptions.LoggerFactory.CreateLogger(executor.Id);
        this.ContinueWith(executor, executor.ParentId, condition, completionHandler);
    }

    private void ContinueWith(
        Executor executor,
        string parentId,
        Func<object?, bool>? condition = null,
        Action? completionHandler = null)
    {
        this._workflowModel.AddNode(executor, parentId, completionHandler);
        this._workflowModel.AddLinkFromPeer(parentId, executor.Id, condition);
    }

    public static string RootId(string? actionId) => $"root_{actionId ?? "workflow"}";

    private static string PostId(string actionId) => $"{actionId}_Post";

    private static string GetParentId(BotElement item) =>
        item.GetParentId() ??
        throw new DeclarativeModelException($"Missing parent ID for action element: {item.GetId()} [{item.GetType().Name}].");

    private string ContinuationFor(string parentId) => this.ContinuationFor(parentId, parentId);

    private string ContinuationFor(string actionId, string parentId)
    {
        actionId = PostId(actionId);
        this._workflowModel.AddNode(this.CreateStep(actionId), parentId);
        return actionId;
    }

    private void RestartAfter(string actionId, string parentId) =>
        this._workflowModel.AddNode(this.CreateStep($"{actionId}_Continue"), parentId);

    private DelegateActionExecutor CreateStep(string actionId, DelegateAction? stepAction = null)
    {
        DelegateActionExecutor stepExecutor = new(actionId, stepAction);

        return stepExecutor;
    }

    private void NotSupported(DialogAction item)
    {
        Debug.WriteLine($"> UNKNOWN: {new string('\t', this._workflowModel.GetDepth(item.GetParentId()))}{FormatItem(item)} => {FormatParent(item)}");
        this.HasUnsupportedActions = true;
    }

    private void Trace(BotElement item)
    {
        Debug.WriteLine($"> VISIT: {new string('\t', this._workflowModel.GetDepth(item.GetParentId()))}{FormatItem(item)} => {FormatParent(item)}");
    }

    private void Trace(DialogAction item)
    {
        string? parentId = item.GetParentId();
        if (item.Id.Equals(parentId ?? string.Empty))
        {
            parentId = RootId(parentId);
        }
        Debug.WriteLine($"> VISIT: {new string('\t', this._workflowModel.GetDepth(parentId))}{FormatItem(item)} => {FormatParent(item)}");
    }

    private static string FormatItem(BotElement element) => $"{element.GetType().Name} ({element.GetId()})";

    private static string FormatParent(BotElement element) =>
        element.Parent is null ?
        throw new DeclarativeModelException($"Undefined parent for {element.GetType().Name} that is member of {element.GetId()}.") :
        $"{element.Parent.GetType().Name} ({element.GetParentId()})";
}
