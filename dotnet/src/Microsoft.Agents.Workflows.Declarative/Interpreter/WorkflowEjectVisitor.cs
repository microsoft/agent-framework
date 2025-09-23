// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Diagnostics;
using Microsoft.Agents.Workflows.Declarative.CodeGen;
using Microsoft.Agents.Workflows.Declarative.Extensions;
using Microsoft.Agents.Workflows.Declarative.Kit;
using Microsoft.Agents.Workflows.Declarative.ObjectModel;
using Microsoft.Agents.Workflows.Declarative.PowerFx;
using Microsoft.Bot.ObjectModel;

namespace Microsoft.Agents.Workflows.Declarative.Interpreter;

internal sealed class WorkflowEjectVisitor : DialogActionVisitor
{
    private readonly string _rootId;
    private readonly WorkflowModel<string> _workflowModel;

    public WorkflowEjectVisitor(
        string workflowId,
        WorkflowTypeInfo typeInfo)
    {
        this._rootId = workflowId;
        this._workflowModel = new WorkflowModel<string>(new RootTemplate(workflowId, typeInfo));
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
                //DelegateAction<ActionExecutorResult>? action = null; // %%% TODO - CONDITION
                //ConditionGroupExecutor? conditionGroup = this._workflowModel.LocateParent<ConditionGroupExecutor>(parentId);
                //if (conditionGroup is not null)
                //{
                //    action = conditionGroup.DoneAsync;
                //}

                // Define post action for this scope
                string completionId = this.ContinuationFor(item.Id.Value);
                this._workflowModel.AddLinkFromPeer(item.Id.Value, completionId);
                // Transition to post action of parent scope
                this._workflowModel.AddLink(completionId, WorkflowActionVisitor.Steps.Post(parentId));
            }
        }
    }

    public override void VisitConditionItem(ConditionItem item) // %%% TODO - CONDITION
    {
        Trace(item);

        //ConditionGroupExecutor? conditionGroup = this._workflowModel.LocateParent<ConditionGroupExecutor>(item.GetParentId());
        //if (conditionGroup is not null)
        //{
        //    string stepId = ConditionGroupExecutor.Steps.Item(conditionGroup.Model, item);
        //    string parentId = GetParentId(item);
        //    this._workflowModel.AddNode(this.CreateStep(stepId), parentId, CompletionHandler);

        //    base.VisitConditionItem(item);

        //    // Complete the condition item.
        //    void CompletionHandler()
        //    {
        //        string completionId = this.ContinuationFor(stepId); // End items
        //        this._workflowModel.AddLink(completionId, PostId(conditionGroup.Id)); // Merge with parent scope

        //        // Merge link when no action group is defined
        //        if (!item.Actions.Any())
        //        {
        //            this._workflowModel.AddLink(stepId, completionId);
        //        }
        //    }
        //}
    }

    protected override void Visit(ConditionGroup item) // %%% TODO - CONDITION
    {
        this.Trace(item);

        //string actionId = item.GetId();
        //this.Executors.Add(new ConditionGroupTemplate(item).TransformText());
        //this.Instances.Add(new InstanceTemplate(actionId, this._rootId).TransformText());

        //this.Edges.Add(new EdgeTemplate("root", actionId).TransformText()); // %%% CONTINUE WITH

        ////ConditionGroupExecutor action = new(item, this._workflowState);
        ////this.ContinueWith(action);
        ////this.ContinuationFor(action.Id, action.ParentId);

        //string? lastConditionItemId = null;
        //foreach (ConditionItem conditionItem in item.Conditions)
        //{
        //    // Create conditional link for conditional action
        //    lastConditionItemId = ConditionGroupExecutor.Steps.Item(item, conditionItem);
        //    this.Edges.Add(new EdgeTemplate(actionId, lastConditionItemId).TransformText()); // %%% CONDITION (result) => action.IsMatch(conditionItem, result));

        //    conditionItem.Accept(this);
        //}

        //if (item.ElseActions?.Actions.Length > 0)
        //{
        //    if (lastConditionItemId is not null)
        //    {
        //        // Create clean start for else action from prior conditions
        //        //this.RestartAfter(lastConditionItemId, action.Id);
        //    }

        //    // Create conditional link for else action
        //    string stepId = ConditionGroupExecutor.Steps.Else(item);
        //    this.Edges.Add(new EdgeTemplate(actionId, stepId).TransformText()); // %%% CONDITION (result) => action.IsElse(result));
        //}
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
        ForeachTemplate template = new(item);
        string loopId = ForeachExecutor.Steps.Next(template.Id);
        this.ContinueWith(template, condition: null, CompletionHandler); // Foreach
        // Transition to select the next item
        this.ContinueWith(new EmptyTemplate(loopId, this._rootId, $"{template.Id.FormatName()}.{nameof(ForeachExecutor.TakeNextAsync)}"), template.Id);

        // Transition to post action if no more items
        string continuationId = this.ContinuationFor(template.Id, template.ParentId); // Action continuation
        this._workflowModel.AddLink(loopId, continuationId, $"!{template.Id.FormatName()}.{nameof(ForeachExecutor.HasValue)}");

        // Transition to start of inner actions if there is a current item
        string startId = ForeachExecutor.Steps.Start(template.Id); // %%% PRUNE - Start really needed at all?
        this._workflowModel.AddNode(new EmptyTemplate(startId, this._rootId), template.Id);
        this._workflowModel.AddLink(loopId, startId, $"{template.Id.FormatName()}.{nameof(ForeachExecutor.HasValue)}");

        void CompletionHandler()
        {
            // Transition to end of inner actions
            string endActionsId = ForeachExecutor.Steps.End(template.Id); // Loop continuation
            this.ContinueWith(new EmptyTemplate(endActionsId, this._rootId, $"{template.Id.FormatName()}.{nameof(ForeachExecutor.ResetAsync)}"), template.Id);
            // Transition to select the next item
            this._workflowModel.AddLink(endActionsId, loopId);
        }
    }

    protected override void Visit(BreakLoop item)
    {
        this.Trace(item);

        // Locate the nearest "Foreach" loop that contains this action
        ForeachTemplate? loopExecutor = this._workflowModel.LocateParent<ForeachTemplate>(item.GetParentId());
        // Skip action if its not contained a loop
        if (loopExecutor is not null)
        {
            // Represent action with default executor
            DefaultTemplate template = new(item, this._rootId);
            this.ContinueWith(template);
            // Transition to post action
            this._workflowModel.AddLink(template.Id, WorkflowActionVisitor.Steps.Post(loopExecutor.Id));
            // Define a clean-start to ensure "break" is not a source for any edge
            this.RestartAfter(template.Id, template.ParentId);
        }
    }

    protected override void Visit(ContinueLoop item)
    {
        this.Trace(item);

        // Locate the nearest "Foreach" loop that contains this action
        ForeachTemplate? loopExecutor = this._workflowModel.LocateParent<ForeachTemplate>(item.GetParentId());
        // Skip action if its not contained a loop
        if (loopExecutor is not null)
        {
            // Represent action with default executor
            DefaultTemplate template = new(item, this._rootId);
            this.ContinueWith(template);
            // Transition to select the next item
            this._workflowModel.AddLink(template.Id, ForeachExecutor.Steps.Start(loopExecutor.Id));
            // Define a clean-start to ensure "continue" is not a source for any edge
            this.RestartAfter(template.Id, template.ParentId);
        }
    }

    protected override void Visit(Question item) // %%% TODO
    {
        this.Trace(item);

        //this.ContinueWith(new QuestionTemplate(item));
    }

    protected override void Visit(EndDialog item)
    {
        this.Trace(item);

        // Represent action with default executor
        DefaultTemplate template = new(item, this._rootId);
        this.ContinueWith(template);
        // Define a clean-start to ensure "end" is not a source for any edge
        this.RestartAfter(template.Id, template.ParentId);
    }

    protected override void Visit(EndConversation item)
    {
        this.Trace(item);

        // Represent action with default executor
        DefaultTemplate template = new(item, this._rootId);
        this.ContinueWith(template);
        // Define a clean-start to ensure "end" is not a source for any edge
        this.RestartAfter(template.Id, template.ParentId);
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

    protected override void Visit(InvokeAzureAgent item) // %%% TODO
    {
        this.Trace(item);

        //this.ContinueWith(new InvokeAzureAgentTemplate(item));
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

    protected override void Visit(EditTable item) // %%% TODO
    {
        this.Trace(item);

        //this.ContinueWith(new EditTableTemplate(item));
    }

    protected override void Visit(EditTableV2 item) // %%% TODO
    {
        this.Trace(item);

        //this.ContinueWith(new EditTableV2Template(item));
    }

    protected override void Visit(ParseValue item) // %%% TODO
    {
        this.Trace(item);

        //this.ContinueWith(new ParseValueTemplate(item));
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
        ActionTemplate template,
        string? condition = null,
        Action? completionHandler = null)
    {
        this.ContinueWith(template, template.ParentId, condition, completionHandler);
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

    private string ContinuationFor(string parentId, DelegateAction<ActionExecutorResult>? stepAction = null) => this.ContinuationFor(parentId, parentId, stepAction);

    private string ContinuationFor(string actionId, string parentId, DelegateAction<ActionExecutorResult>? stepAction = null)
    {
        actionId = WorkflowActionVisitor.Steps.Post(actionId);

        this._workflowModel.AddNode(new EmptyTemplate(actionId, this._rootId), parentId);

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

    private static void Trace(BotElement item)
    {
        Debug.WriteLine($"> VISIT: {FormatItem(item)} => {FormatParent(item)}");
    }

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
