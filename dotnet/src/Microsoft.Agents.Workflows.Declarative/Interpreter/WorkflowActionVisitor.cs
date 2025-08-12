// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Diagnostics;
using System.Linq;
using System.Threading.Tasks;
using Microsoft.Agents.Workflows.Core;
using Microsoft.Agents.Workflows.Declarative.Execution;
using Microsoft.Agents.Workflows.Declarative.Extensions;
using Microsoft.Agents.Workflows.Declarative.PowerFx;
using Microsoft.Bot.ObjectModel;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.Workflows.Declarative.Interpreter;

internal sealed class WorkflowActionVisitor : DialogActionVisitor
{
    private readonly WorkflowBuilder _workflowBuilder;
    private readonly WorkflowModel _workflowModel;
    private readonly DeclarativeWorkflowContext _workflowContext;
    private readonly WorkflowScopes _scopes;
    private readonly WorkflowExecutionContext _executionContext;

    public WorkflowActionVisitor(
        ExecutorIsh rootAction,
        DeclarativeWorkflowContext workflowContext,
        WorkflowScopes scopes)
    {
        this._workflowModel = new WorkflowModel(rootAction);
        this._workflowBuilder = new WorkflowBuilder(rootAction);
        this._workflowContext = workflowContext;
        this._scopes = scopes;

        this._executionContext = workflowContext.CreateActionContext(rootAction.Id, scopes);
    }

    public bool HasUnsupportedActions { get; private set; }

    public Workflow<string> Complete()
    {
        // Process the cached links
        this._workflowModel.ConnectNodes(this._workflowBuilder);

        // Build final workflow
        return this._workflowBuilder.Build<string>();
    }

    protected override void Visit(ActionScope item)
    {
        this.Trace(item);

        string parentId = Throw.IfNull(item.GetParentId(), nameof(BotElement.Parent));
        if (item.Id.Equals(parentId))
        {
            parentId = $"root_{parentId}";
        }
        this.ContinueWith(this.CreateStep(item.Id.Value, nameof(ActionScope)), parentId, condition: null, CompletionHandler);

        void CompletionHandler()
        {
            if (this._workflowModel.GetDepth(item.Id.Value) > 1)
            {
                string completionId = RestartId(item.Id.Value);
                this.ContinueWith(this.CreateStep(completionId, $"{nameof(ActionScope)}_Post"), item.Id.Value);
                this._workflowModel.AddLink(completionId, RestartId(parentId));
            }
        }
    }

    public override void VisitConditionItem(ConditionItem item)
    {
        this.Trace(item);

        Func<object?, bool>? condition = null;

        if (item.Condition is not null)
        {
            // %%% BUG: ONLY ONE (FIRST) CONDITION
            condition =
                new((_) =>
                {
                    bool result = this._executionContext.Engine.Eval(item.Condition.ExpressionText ?? "true").AsBoolean();
                    Debug.WriteLine($"!!! CONDITION: {item.Condition.ExpressionText ?? "true"}={result}");
                    return result;
                });
        }

        string stepId = item.Id ?? $"{nameof(ConditionItem)}_{Guid.NewGuid():N}";
        string parentId = Throw.IfNull(item.GetParentId(), nameof(BotElement.Parent));

        WorkflowDelegateExecutor executor = this.CreateStep(stepId, nameof(ConditionItem));
        this._workflowModel.AddNode(executor, parentId, CompletionHandler);
        this._workflowModel.AddLink(parentId, stepId, condition);

        base.VisitConditionItem(item);

        void CompletionHandler()
        {
            string completionId = this.RestartFrom(stepId, nameof(ConditionItem), parentId);
            this._workflowModel.AddLink(completionId, RestartId(parentId));

            if (!item.Actions.Any())
            {
                this._workflowModel.AddLink(stepId, completionId);
            }
        }
    }

    protected override void Visit(ConditionGroup item)
    {
        this.Trace(item);

        ConditionGroupExecutor action = new(item);
        this.ContinueWith(action);
        this.RestartFrom(action.Id, nameof(ConditionGroupExecutor), action.ParentId);

        // %%% SUPPORT: item.ElseActions

        int index = 1;
        foreach (ConditionItem conditionItem in item.Conditions)
        {
            // Visit each action in the condition item
            conditionItem.Accept(this);

            ++index;
        }
    }

    protected override void Visit(GotoAction item)
    {
        this.Trace(item);

        string parentId = Throw.IfNull(item.GetParentId(), nameof(BotElement.Parent));
        this.ContinueWith(this.CreateStep(item.Id.Value, nameof(GotoAction)), parentId);
        this._workflowModel.AddLink(item.Id.Value, item.ActionId.Value);
        this.RestartFrom(item.Id.Value, nameof(GotoAction), parentId);
    }

    protected override void Visit(Foreach item)
    {
        this.Trace(item);

        ForeachExecutor action = new(item);
        string loopId = ForeachExecutor.Steps.Next(action.Id);
        this.ContinueWith(action, condition: null, CompletionHandler);
        string restartId = this.RestartFrom(action);
        this.ContinueWith(this.CreateStep(loopId, $"{nameof(ForeachExecutor)}_Next", action.TakeNext), action.Id);
        this._workflowModel.AddLink(loopId, restartId, (_) => !action.HasValue);
        this.ContinueWith(this.CreateStep(ForeachExecutor.Steps.Start(action.Id), $"{nameof(ForeachExecutor)}_Start"), action.Id, (_) => action.HasValue);

        void CompletionHandler()
        {
            string completionId = ForeachExecutor.Steps.End(action.Id);
            this.ContinueWith(this.CreateStep(completionId, $"{nameof(ForeachExecutor)}_End"), action.Id);
            this._workflowModel.AddLink(completionId, loopId);
        }
    }

    protected override void Visit(BreakLoop item)
    {
        this.Trace(item);

        string? loopId = this._workflowModel.LocateParent<ForeachExecutor>(item.GetParentId());
        if (loopId is not null)
        {
            string parentId = Throw.IfNull(item.GetParentId(), nameof(BotElement.Parent));
            this.ContinueWith(this.CreateStep(item.Id.Value, nameof(BreakLoop)), parentId);
            this._workflowModel.AddLink(item.Id.Value, RestartId(loopId));
            this.RestartFrom(item.Id.Value, nameof(BreakLoop), parentId);
        }
    }

    protected override void Visit(ContinueLoop item)
    {
        this.Trace(item);

        string? loopId = this._workflowModel.LocateParent<ForeachExecutor>(item.GetParentId());
        if (loopId is not null)
        {
            string parentId = Throw.IfNull(item.GetParentId(), nameof(BotElement.Parent));
            this.ContinueWith(this.CreateStep(item.Id.Value, nameof(ContinueLoop)), parentId);
            this._workflowModel.AddLink(item.Id.Value, ForeachExecutor.Steps.Next(loopId));
            this.RestartFrom(item.Id.Value, nameof(ContinueLoop), parentId);
        }
    }

    protected override void Visit(EndConversation item)
    {
        this.Trace(item);

        EndConversationExecutor action = new(item);
        this.ContinueWith(action);
        this.RestartFrom(action);
    }

    protected override void Visit(AnswerQuestionWithAI item)
    {
        this.Trace(item);

        this.ContinueWith(new AnswerQuestionWithAIExecutor(item));
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

        this.ContinueWith(new SendActivityExecutor(item, this._workflowContext.ActivityChannel));
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
        executor.Attach(this._executionContext);
        this.ContinueWith(executor, executor.ParentId, condition, completionHandler);
    }

    private void ContinueWith(
        ExecutorBase executor,
        string parentId,
        Func<object?, bool>? condition = null,
        Action? completionHandler = null)
    {
        this._workflowModel.AddNode(executor, parentId, completionHandler);
        this._workflowModel.AddLinkFromPeer(parentId, executor.Id, condition);
    }

    private static string RestartId(string actionId) => $"{actionId}_Post";

    private string RestartFrom(WorkflowActionExecutor executor) =>
        this.RestartFrom(executor.Id, executor.GetType().Name, executor.ParentId);

    private string RestartFrom(string actionId, string name, string parentId)
    {
        string restartId = RestartId(actionId);
        this._workflowModel.AddNode(this.CreateStep(restartId, $"{name}_Post"), parentId);
        return restartId;
    }

    private WorkflowDelegateExecutor CreateStep(string actionId, string name, Action<WorkflowExecutionContext>? stepAction = null)
    {
        WorkflowDelegateExecutor stepExecutor =
            new(actionId,
                () =>
                {
                    stepAction?.Invoke(this._executionContext);
                    return new ValueTask();
                });

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
