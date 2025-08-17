// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Diagnostics;
using System.Linq;
using Microsoft.Agents.Workflows.Declarative.Extensions;
using Microsoft.Agents.Workflows.Declarative.ObjectModel;
using Microsoft.Bot.ObjectModel;
using Microsoft.Shared.Diagnostics;
using static System.Collections.Specialized.BitVector32;

namespace Microsoft.Agents.Workflows.Declarative.Interpreter;

internal sealed class WorkflowActionVisitor : DialogActionVisitor
{
    private readonly WorkflowBuilder _workflowBuilder;
    private readonly WorkflowModel _workflowModel;
    private readonly DeclarativeWorkflowContext _workflowContext;

    public WorkflowActionVisitor(
        Executor rootAction,
        DeclarativeWorkflowContext workflowContext)
    {
        this._workflowModel = new WorkflowModel(rootAction);
        this._workflowBuilder = new WorkflowBuilder(rootAction);
        this._workflowContext = workflowContext;
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

        string parentId = Throw.IfNull(item.GetParentId(), nameof(BotElement.Parent));

        // %%% COMMENTS
        if (item.Id.Equals(parentId))
        {
            parentId = $"root_{parentId}";
        }

        this.ContinueWith(this.CreateStep(item.Id.Value), parentId, condition: null, CompletionHandler);

        // %%% COMMENTS
        void CompletionHandler()
        {
            if (this._workflowModel.GetDepth(item.Id.Value) > 1)
            {
                string completionId = RestartId(item.Id.Value); // %%% RESTART: FALSE
                this.ContinueWith(this.CreateStep(completionId), item.Id.Value);
                this._workflowModel.AddLink(completionId, RestartId(parentId)); // %%% RESTART: FALSE
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
            string parentId = Throw.IfNull(item.GetParentId(), nameof(BotElement.Parent));
            this._workflowModel.AddNode(this.CreateStep(stepId), parentId, CompletionHandler);

            base.VisitConditionItem(item);

            // %%% COMMENTS
            void CompletionHandler()
            {
                string completionId = this.RestartAfter(stepId, parentId); // %%% RESTART: FALSE
                this._workflowModel.AddLink(completionId, RestartId(parentId)); // %%% RESTART: FALSE

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

        ConditionGroupExecutor action = new(item);
        this.ContinueWith(action);
        this.RestartAfter(action); // %%% RESTART: FALSE

        foreach (ConditionItem conditionItem in item.Conditions)
        {
            string stepId = ConditionGroupExecutor.Steps.Item(item, conditionItem);
            this._workflowModel.AddLink(action.Id, stepId, (result) => action.IsMatch(conditionItem, result));

            conditionItem.Accept(this);
        }

        if (item.ElseActions?.Actions.Length > 0)
        {
            string stepId = ConditionGroupExecutor.Steps.Else(item);
            this._workflowModel.AddLink(action.Id, stepId, (result) => action.IsElse(result));
        }
    }

    protected override void Visit(GotoAction item)
    {
        this.Trace(item);

        string parentId = Throw.IfNull(item.GetParentId(), nameof(BotElement.Parent));
        this.ContinueWith(this.CreateStep(item.Id.Value), parentId);
        this._workflowModel.AddLink(item.Id.Value, item.ActionId.Value);
        this.RestartAfter(item.Id.Value, parentId); // %%% RESTART: TRUE
    }

    protected override void Visit(Foreach item)
    {
        this.Trace(item);

        ForeachExecutor action = new(item);
        string loopId = ForeachExecutor.Steps.Next(action.Id);
        this.ContinueWith(action, condition: null, CompletionHandler);
        string restartId = this.RestartAfter(action); // %%% RESTART: FALSE
        this.ContinueWith(this.CreateStep(loopId, action.TakeNext), action.Id);
        this._workflowModel.AddLink(loopId, restartId, (_) => !action.HasValue);
        this.ContinueWith(this.CreateStep(ForeachExecutor.Steps.Start(action.Id)), action.Id, (_) => action.HasValue);

        void CompletionHandler()
        {
            string completionId = ForeachExecutor.Steps.End(action.Id);
            this.ContinueWith(this.CreateStep(completionId, action.Reset), action.Id);
            this._workflowModel.AddLink(completionId, loopId);
        }
    }

    protected override void Visit(BreakLoop item)
    {
        this.Trace(item);

        ForeachExecutor? loopExecutor = this._workflowModel.LocateParent<ForeachExecutor>(item.GetParentId());
        if (loopExecutor is not null)
        {
            string parentId = Throw.IfNull(item.GetParentId(), nameof(BotElement.Parent));
            this.ContinueWith(this.CreateStep(item.Id.Value), parentId);
            this._workflowModel.AddLink(item.Id.Value, RestartId(loopExecutor.Id)); // %%% RESTART: TRUE
            this.RestartAfter(item.Id.Value, parentId);
        }
    }

    protected override void Visit(ContinueLoop item)
    {
        this.Trace(item);

        ForeachExecutor? loopExecutor = this._workflowModel.LocateParent<ForeachExecutor>(item.GetParentId());
        if (loopExecutor is not null)
        {
            string parentId = Throw.IfNull(item.GetParentId(), nameof(BotElement.Parent));
            this.ContinueWith(this.CreateStep(item.Id.Value), parentId);
            this._workflowModel.AddLink(item.Id.Value, ForeachExecutor.Steps.Next(loopExecutor.Id));
            this.RestartAfter(item.Id.Value, parentId); // %%% RESTART: TRUE
        }
    }

    protected override void Visit(EndConversation item)
    {
        this.Trace(item);

        string parentId = Throw.IfNull(item.GetParentId(), nameof(BotElement.Parent));
        this.ContinueWith(this.CreateStep(item.Id.Value), parentId);
        this.RestartAfter(item.Id.Value, parentId); // %%% RESTART: TRUE
    }

    protected override void Visit(AnswerQuestionWithAI item)
    {
        this.Trace(item);

        this.ContinueWith(new AnswerQuestionWithAIExecutor(item, this._workflowContext.CreateClient()));
    }

    protected override void Visit(SetVariable item)
    {
        this.Trace(item);

        this.ContinueWith(new SetVariableExecutor(item));
    }

    protected override void Visit(SetTextVariable item)
    {
        this.Trace(item);

        this.ContinueWith(new SetTextVariableExecutor(item));
    }

    protected override void Visit(ClearAllVariables item)
    {
        this.Trace(item);

        this.ContinueWith(new ClearAllVariablesExecutor(item));
    }

    protected override void Visit(ResetVariable item)
    {
        this.Trace(item);

        this.ContinueWith(new ResetVariableExecutor(item));
    }

    protected override void Visit(EditTable item) // %%% SUPPORT: EditTable
    {
        this.Trace(item);
    }

    protected override void Visit(EditTableV2 item)
    {
        this.Trace(item);

        this.ContinueWith(new EditTableV2Executor(item));
    }

    protected override void Visit(ParseValue item)
    {
        this.Trace(item);

        this.ContinueWith(new ParseValueExecutor(item));
    }

    protected override void Visit(SendActivity item)
    {
        this.Trace(item);

        this.ContinueWith(new SendActivityExecutor(item));
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
        executor.Logger = this._workflowContext.LoggerFactory.CreateLogger(executor.Id);
        executor.WorkflowContext = this._workflowContext; // %%% HAXX: Initial state
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

    private static string RestartId(string actionId) => $"{actionId}_Post";

    private string RestartAfter(WorkflowActionExecutor executor) =>
        this.RestartAfter(executor.Id, executor.ParentId);

    private string RestartAfter(string actionId, string parentId)
    {
        string restartId = RestartId(actionId);
        this._workflowModel.AddNode(this.CreateStep(restartId), parentId);
        return restartId;
    }

    private DelegateActionExecutor CreateStep(string actionId, Action? stepAction = null)
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
            parentId = $"root_{parentId}";
        }
        Debug.WriteLine($"> VISIT: {new string('\t', this._workflowModel.GetDepth(parentId))}{FormatItem(item)} => {FormatParent(item)}");
    }

    private static string FormatItem(BotElement element) => $"{element.GetType().Name} ({element.GetId()})";

    private static string FormatParent(BotElement element) =>
        element.Parent is null ?
        throw new WorkflowModelException($"Undefined parent for {element.GetType().Name} that is member of {element.GetId()}.") :
        $"{element.Parent.GetType().Name} ({element.GetParentId()})";
}
