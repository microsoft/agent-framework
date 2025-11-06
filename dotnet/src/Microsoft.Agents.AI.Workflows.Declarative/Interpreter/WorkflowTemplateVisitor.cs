// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Diagnostics;
using System.Linq;
using Microsoft.Agents.AI.Workflows.Declarative.CodeGen;
using Microsoft.Agents.AI.Workflows.Declarative.Extensions;
using Microsoft.Agents.AI.Workflows.Declarative.ObjectModel;
using Microsoft.Agents.AI.Workflows.Declarative.PowerFx;
using Microsoft.Bot.ObjectModel;

namespace Microsoft.Agents.AI.Workflows.Declarative.Interpreter;

internal sealed class WorkflowTemplateVisitor : DialogActionVisitor
{
    private readonly string _rootId;
    private readonly WorkflowModel<string> _workflowModel;

    public WorkflowTemplateVisitor(
        string workflowId,
        WorkflowTypeInfo typeInfo)
    {
        this._rootId = workflowId;
        this._workflowModel = new WorkflowModel<string>(new RootTemplate(workflowId, typeInfo));

        WorkflowDiagnostics.SetFoundryProduct();
    }

    public bool HasUnsupportedActions { get; private set; }

    public string Complete(string? workflowNamespace = null, string? workflowPrefix = null)
    {
        WorkflowCodeBuilder builder = new(this._rootId);

        this._workflowModel.Build(builder);

        return builder.GenerateCode(workflowNamespace, workflowPrefix);
    }

    protected override void Visit(ActionScope item)
    {
        this.Trace(item);

        string parentId = GetParentId(item);

        // Handle case where root element is its own parent
        if (item.Id.Equals(parentId))
        {
            parentId = WorkflowActionVisitor.Steps.Root(parentId);
        }

        this.ContinueWith(new EmptyTemplate(item.Id.Value, this._rootId), parentId, condition: null, CompletionHandler);

        //// Complete the action scope.
        void CompletionHandler()
        {
            // No completion for root scope
            if (this._workflowModel.GetDepth(item.Id.Value) > 1)
            {
                // Define post action for this scope
                string completionId = this.ContinuationFor(item.Id.Value);
                this._workflowModel.AddLinkFromPeer(item.Id.Value, completionId);
                // Transition to post action of parent scope
                this._workflowModel.AddLink(completionId, WorkflowActionVisitor.Steps.Post(parentId));
            }
        }
    }

    public override void VisitConditionItem(ConditionItem item)
    {
        this.Trace(item);

        string parentId = GetParentId(item);
        ConditionGroupTemplate? conditionGroup = this._workflowModel.LocateParent<ConditionGroupTemplate>(parentId);
        if (conditionGroup is not null)
        {
            string stepId = ConditionGroupExecutor.Steps.Item(conditionGroup.Model, item);
            this._workflowModel.AddNode(new EmptyTemplate(stepId, this._rootId), parentId, CompletionHandler);

            base.VisitConditionItem(item);

            // Complete the condition item.
            void CompletionHandler()
            {
                string completionId = this.ContinuationFor(stepId);
                this._workflowModel.AddLink(completionId, WorkflowActionVisitor.Steps.Post(conditionGroup.Id));

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

        ConditionGroupTemplate action = new(item);
        this.ContinueWith(action);
        this.ContinuationFor(action.Id, parentId: action.ParentId);

        string? lastConditionItemId = null;
        foreach (ConditionItem conditionItem in item.Conditions)
        {
            // Create conditional link for conditional action
            lastConditionItemId = ConditionGroupExecutor.Steps.Item(item, conditionItem);
            this._workflowModel.AddLink(action.Id, lastConditionItemId, $@"ActionExecutor.IsMatch(""{lastConditionItemId}"", result)");

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
            this._workflowModel.AddLink(action.Id, stepId, $@"ActionExecutor.IsMatch(""{stepId}"", result)");
        }
    }

    protected override void Visit(GotoAction item)
    {
        this.Trace(item);

        // Represent action with default executor
        DefaultTemplate action = new(item, this._rootId);
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
        ForeachTemplate action = new(item);
        string loopId = ForeachExecutor.Steps.Next(action.Id);
        this.ContinueWith(action, condition: null, CompletionHandler); // Foreach
        // Transition to select the next item
        this.ContinueWith(new EmptyTemplate(loopId, this._rootId, $"{action.Id.FormatName()}.{nameof(ForeachExecutor.TakeNextAsync)}"), action.Id);

        // Transition to post action if no more items
        string continuationId = this.ContinuationFor(action.Id, parentId: action.ParentId); // Action continuation
        this._workflowModel.AddLink(loopId, continuationId, $"!{action.Id.FormatName()}.{nameof(ForeachExecutor.HasValue)}");

        // Transition to start of inner actions if there is a current item
        string startId = ForeachExecutor.Steps.Start(action.Id);
        this._workflowModel.AddNode(new EmptyTemplate(startId, this._rootId), action.Id);
        this._workflowModel.AddLink(loopId, startId, $"{action.Id.FormatName()}.{nameof(ForeachExecutor.HasValue)}");

        void CompletionHandler()
        {
            // Transition to end of inner actions
            string endActionsId = ForeachExecutor.Steps.End(action.Id); // Loop continuation
            this.ContinueWith(new EmptyTemplate(endActionsId, this._rootId, $"{action.Id.FormatName()}.{nameof(ForeachExecutor.ResetAsync)}"), action.Id);
            // Transition to select the next item
            this._workflowModel.AddLink(endActionsId, loopId);
        }
    }

    protected override void Visit(BreakLoop item)
    {
        this.Trace(item);

        // Locate the nearest "Foreach" loop that contains this action
        ForeachTemplate? loopAction = this._workflowModel.LocateParent<ForeachTemplate>(item.GetParentId());
        // Skip action if its not contained a loop
        if (loopAction is not null)
        {
            // Represent action with default executor
            DefaultTemplate action = new(item, this._rootId);
            this.ContinueWith(action);
            // Transition to post action
            this._workflowModel.AddLink(action.Id, WorkflowActionVisitor.Steps.Post(loopAction.Id));
            // Define a clean-start to ensure "break" is not a source for any edge
            this.RestartAfter(action.Id, action.ParentId);
        }
    }

    protected override void Visit(ContinueLoop item)
    {
        this.Trace(item);

        // Locate the nearest "Foreach" loop that contains this action
        ForeachTemplate? loopAction = this._workflowModel.LocateParent<ForeachTemplate>(item.GetParentId());
        // Skip action if its not contained a loop
        if (loopAction is not null)
        {
            // Represent action with default executor
            DefaultTemplate action = new(item, this._rootId);
            this.ContinueWith(action);
            // Transition to select the next item
            this._workflowModel.AddLink(action.Id, ForeachExecutor.Steps.Start(loopAction.Id));
            // Define a clean-start to ensure "continue" is not a source for any edge
            this.RestartAfter(action.Id, action.ParentId);
        }
    }

    protected override void Visit(Question item)
    {
        this.NotSupported(item);
    }

    protected override void Visit(RequestExternalInput item)
    {
        this.NotSupported(item);
    }

    protected override void Visit(EndDialog item)
    {
        this.Trace(item);

        // Represent action with default executor
        DefaultTemplate action = new(item, this._rootId);
        this.ContinueWith(action);
        // Define a clean-start to ensure "end" is not a source for any edge
        this.RestartAfter(action.Id, action.ParentId);
    }

    protected override void Visit(EndConversation item)
    {
        this.Trace(item);

        // Represent action with default executor
        DefaultTemplate action = new(item, this._rootId);
        this.ContinueWith(action);
        // Define a clean-start to ensure "end" is not a source for any edge
        this.RestartAfter(action.Id, action.ParentId);
    }

    protected override void Visit(CancelAllDialogs item)
    {
        // Represent action with default executor
        DefaultTemplate action = new(item, this._rootId);
        this.ContinueWith(action);
        // Define a clean-start to ensure "end" is not a source for any edge
        this.RestartAfter(action.Id, action.ParentId);
    }

    protected override void Visit(CancelDialog item)
    {
        // Represent action with default executor
        DefaultTemplate action = new(item, this._rootId);
        this.ContinueWith(action);
        // Define a clean-start to ensure "end" is not a source for any edge
        this.RestartAfter(action.Id, action.ParentId);
    }

    protected override void Visit(CreateConversation item)
    {
        this.Trace(item);

        this.ContinueWith(new CreateConversationTemplate(item));
    }

    protected override void Visit(AddConversationMessage item)
    {
        this.Trace(item);

        this.ContinueWith(new AddConversationMessageTemplate(item));
    }

    protected override void Visit(CopyConversationMessages item)
    {
        this.Trace(item);

        this.ContinueWith(new CopyConversationMessagesTemplate(item));
    }

    protected override void Visit(InvokeAzureAgent item)
    {
        this.Trace(item);

        this.ContinueWith(new InvokeAzureAgentTemplate(item));
    }

    protected override void Visit(InvokeAzureResponse item)
    {
        this.NotSupported(item);
    }

    protected override void Visit(RetrieveConversationMessage item)
    {
        this.Trace(item);

        this.ContinueWith(new RetrieveConversationMessageTemplate(item));
    }

    protected override void Visit(RetrieveConversationMessages item)
    {
        this.Trace(item);

        this.ContinueWith(new RetrieveConversationMessagesTemplate(item));
    }

    protected override void Visit(SetVariable item)
    {
        this.Trace(item);

        this.ContinueWith(new SetVariableTemplate(item));
    }

    protected override void Visit(SetMultipleVariables item)
    {
        this.Trace(item);

        this.ContinueWith(new SetMultipleVariablesTemplate(item));
    }

    protected override void Visit(SetTextVariable item)
    {
        this.Trace(item);

        this.ContinueWith(new SetTextVariableTemplate(item));
    }

    protected override void Visit(ClearAllVariables item)
    {
        this.Trace(item);

        this.ContinueWith(new ClearAllVariablesTemplate(item));
    }

    protected override void Visit(ResetVariable item)
    {
        this.Trace(item);

        this.ContinueWith(new ResetVariableTemplate(item));
    }

    protected override void Visit(EditTable item)
    {
        this.NotSupported(item);
    }

    protected override void Visit(EditTableV2 item)
    {
        this.NotSupported(item);
    }

    protected override void Visit(ParseValue item)
    {
        this.Trace(item);

        this.ContinueWith(new ParseValueTemplate(item));
    }

    protected override void Visit(SendActivity item)
    {
        this.Trace(item);

        this.ContinueWith(new SendActivityTemplate(item));
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
        ActionTemplate action,
        string? condition = null,
        Action? completionHandler = null)
    {
        this.ContinueWith(action, action.ParentId, condition, completionHandler);
    }

    private void ContinueWith(
        IModeledAction action,
        string parentId,
        string? condition = null,
        Action? completionHandler = null)
    {
        this._workflowModel.AddNode(action, parentId, completionHandler);
        this._workflowModel.AddLinkFromPeer(parentId, action.Id, condition);
    }

    private string ContinuationFor(string parentId, string? stepAction = null) => this.ContinuationFor(parentId, parentId, stepAction);

    private string ContinuationFor(string actionId, string parentId, string? stepAction = null)
    {
        actionId = WorkflowActionVisitor.Steps.Post(actionId);

        this._workflowModel.AddNode(new EmptyTemplate(actionId, this._rootId, stepAction), parentId);

        return actionId;
    }

    private void RestartAfter(string actionId, string parentId) =>
        this._workflowModel.AddNode(new EmptyTemplate(WorkflowActionVisitor.Steps.Restart(actionId), this._rootId), parentId);

    private static string GetParentId(BotElement item) =>
        item.GetParentId() ??
        throw new DeclarativeModelException($"Missing parent ID for action element: {item.GetId()} [{item.GetType().Name}].");

    private void NotSupported(DialogAction item)
    {
        Debug.WriteLine($"> UNKNOWN: {FormatItem(item)} => {FormatParent(item)}");
        this.HasUnsupportedActions = true;
    }

    private void Trace(BotElement item) =>
        Debug.WriteLine($"> VISIT: {new string('\t', this._workflowModel.GetDepth(item.GetParentId()))}{FormatItem(item)} => {FormatParent(item)}");

    private void Trace(DialogAction item)
    {
        string? parentId = item.GetParentId();
        if (item.Id.Equals(parentId ?? string.Empty))
        {
            parentId = WorkflowActionVisitor.Steps.Root(parentId);
        }

        Debug.WriteLine($"> VISIT: {new string('\t', this._workflowModel.GetDepth(parentId))}{FormatItem(item)} => {FormatParent(item)}");
    }

    private static string FormatItem(BotElement element) => $"{element.GetType().Name} ({element.GetId()})";

    private static string FormatParent(BotElement element) =>
        element.Parent is null ?
        throw new DeclarativeModelException($"Undefined parent for {element.GetType().Name} that is member of {element.GetId()}.") :
        $"{element.Parent.GetType().Name} ({element.GetParentId()})";
}
