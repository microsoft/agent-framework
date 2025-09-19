// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Diagnostics;
using Microsoft.Agents.Workflows.Declarative.CodeGen;
using Microsoft.Agents.Workflows.Declarative.Extensions;
using Microsoft.Agents.Workflows.Declarative.ObjectModel;
using Microsoft.Agents.Workflows.Declarative.PowerFx;
using Microsoft.Bot.ObjectModel;

namespace Microsoft.Agents.Workflows.Declarative.Interpreter;

internal sealed class WorkflowEjectVisitor : DialogActionVisitor
{
    //private readonly DeclarativeWorkflowModel _workflowModel;

    public WorkflowEjectVisitor(
        string workflowId,
        WorkflowTypeInfo typeInfo)
    {
        //this._workflowModel = new DeclarativeWorkflowModel(rootAction);
        this.Edges = [];
        this.Executors = [new RootTemplate(workflowId, typeInfo).TransformText()];
        this.Instances = [];
    }

    public bool HasUnsupportedActions { get; private set; }

    public List<string> Edges { get; }
    public List<string> Executors { get; }
    public List<string> Instances { get; }

    protected override void Visit(ActionScope item) // %%% TODO
    {
        this.Trace(item);

        //string parentId = GetParentId(item);

        //// Handle case where root element is its own parent
        //if (item.Id.Equals(parentId))
        //{
        //    parentId = RootId(parentId);
        //}

        //this.ContinueWith(this.CreateStep(item.Id.Value), parentId, condition: null, CompletionHandler);

        //// Complete the action scope.
        //void CompletionHandler()
        //{
        //    if (this._workflowModel.GetDepth(item.Id.Value) > 1)
        //    {
        //        string completionId = this.ContinuationFor(item.Id.Value); // End scope
        //        this._workflowModel.AddLinkFromPeer(item.Id.Value, completionId); // Connect with final action
        //        this._workflowModel.AddLink(completionId, PostId(parentId)); // Merge with parent scope
        //    }
        //}
    }

    public override void VisitConditionItem(ConditionItem item) // %%% TODO
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

    protected override void Visit(ConditionGroup item) // %%% TODO
    {
        this.Trace(item);

        string actionId = item.GetId();
        this.Executors.Add(new ConditionGroupTemplate(item).TransformText());
        this.Instances.Add(new InstanceTemplate(actionId).TransformText());

        this.Edges.Add(new EdgeTemplate("root", actionId).TransformText()); // %%% CONTINUE WITH

        //ConditionGroupExecutor action = new(item, this._workflowState);
        //this.ContinueWith(action);
        //this.ContinuationFor(action.Id, action.ParentId);

        string? lastConditionItemId = null;
        foreach (ConditionItem conditionItem in item.Conditions)
        {
            // Create conditional link for conditional action
            lastConditionItemId = ConditionGroupExecutor.Steps.Item(item, conditionItem);
            this.Edges.Add(new EdgeTemplate(actionId, lastConditionItemId).TransformText()); // %%% CONDITION (result) => action.IsMatch(conditionItem, result));

            conditionItem.Accept(this);
        }

        if (item.ElseActions?.Actions.Length > 0)
        {
            if (lastConditionItemId is not null)
            {
                // Create clean start for else action from prior conditions
                //this.RestartAfter(lastConditionItemId, action.Id);
            }

            // Create conditional link for else action
            string stepId = ConditionGroupExecutor.Steps.Else(item);
            this.Edges.Add(new EdgeTemplate(actionId, stepId).TransformText()); // %%% CONDITION (result) => action.IsElse(result));
        }
    }

    protected override void Visit(GotoAction item)
    {
        this.Trace(item);

        string ExecutorComment = @$"Transfers execution to action ""{item.ActionId.Value}""";

        this.Executors.Add(new EmptyTemplate(item, ExecutorComment).TransformText());
        this.Instances.Add(new InstanceTemplate(item.GetId()).TransformText());
        this.Edges.Add(new EdgeTemplate("root", item.GetId()).TransformText()); // %%% CONTINUE WITH
        this.Edges.Add(new EdgeTemplate(item.ActionId.Value, item.GetId()).TransformText()); // %%% RESTART
    }

    protected override void Visit(Foreach item)
    {
        this.Trace(item);

        string actionId = item.GetId();
        string loopId = ForeachExecutor.Steps.Next(actionId);
        string startId = ForeachExecutor.Steps.Next(actionId);
        string endId = ForeachExecutor.Steps.End(actionId);

        this.Executors.Add(new ForeachTemplate(item).TransformText());
        this.Instances.Add(new InstanceTemplate(actionId).TransformText());

        this.Edges.Add(new EdgeTemplate("root", actionId).TransformText()); // %%% CONTINUE WITH
        this.Edges.Add(new EdgeTemplate(actionId, loopId).TransformText()); // %%% CONTINUE WITH
        this.Edges.Add(new EdgeTemplate(loopId, startId).TransformText()); // %%% CONDITION
        this.Edges.Add(new EdgeTemplate(loopId, endId).TransformText()); // %%% CONDITION

        CompletionHandler(); // %%% HAXX

        void CompletionHandler()
        {
            this.Edges.Add(new EdgeTemplate(endId, loopId).TransformText()); // %%% CONTINUE WITH
        }
    }

    protected override void Visit(BreakLoop item)
    {
        this.Trace(item);

        //ForeachExecutor? loopExecutor = this._workflowModel.LocateParent<ForeachExecutor>(item.GetParentId());
        const string LoopId = "loop_action_id"; // %%% TODO
        //if (loopExecutor is not null)
        //{
        string ExecutorComment = @$"Break out of loop: ""{LoopId}""";

        this.Executors.Add(new EmptyTemplate(item, ExecutorComment).TransformText());
        this.Instances.Add(new InstanceTemplate(item.GetId()).TransformText());
        this.Edges.Add(new EdgeTemplate("root", ForeachExecutor.Steps.End(LoopId)).TransformText()); // %%% CONTINUE WITH
        //}
    }

    protected override void Visit(ContinueLoop item)
    {
        this.Trace(item);

        //ForeachExecutor? loopExecutor = this._workflowModel.LocateParent<ForeachExecutor>(item.GetParentId());
        const string LoopId = "loop_action_id"; // %%% TODO
        //if (loopExecutor is not null)
        //{
        string ExecutorComment = @$"Continue with next value for loop: ""{LoopId}""";

        this.Executors.Add(new EmptyTemplate(item, ExecutorComment).TransformText());
        this.Instances.Add(new InstanceTemplate(item.GetId()).TransformText());
        this.Edges.Add(new EdgeTemplate("root", ForeachExecutor.Steps.Start(LoopId)).TransformText()); // %%% CONTINUE WITH
        //}
    }

    protected override void Visit(EndConversation item)
    {
        this.Trace(item);

        const string ExecutorComment = "Ends the conversation with the user. This action does not delete any conversation history.";

        this.Executors.Add(new EmptyTemplate(item, ExecutorComment).TransformText());
        this.Instances.Add(new InstanceTemplate(item.GetId()).TransformText());
        this.Edges.Add(new EdgeTemplate("root", item.GetId()).TransformText()); // %%% CONTINUE WITH AND RESTART
    }

    protected override void Visit(SetVariable item)
    {
        this.Trace(item);

        this.Executors.Add(new SetVariableTemplate(item).TransformText());
        this.Instances.Add(new InstanceTemplate(item.GetId()).TransformText());
        this.Edges.Add(new EdgeTemplate("root", item.GetId()).TransformText()); // %%% CONTINUE WITH
    }

    protected override void Visit(SetMultipleVariables item)
    {
        throw new System.NotImplementedException();
    }

    protected override void Visit(SetTextVariable item)
    {
        this.Trace(item);

        this.Executors.Add(new SetTextVariableTemplate(item).TransformText());
        this.Instances.Add(new InstanceTemplate(item.GetId()).TransformText());
        this.Edges.Add(new EdgeTemplate("root", item.GetId()).TransformText()); // %%% CONTINUE WITH
    }

    protected override void Visit(ClearAllVariables item)
    {
        this.Trace(item);

        this.Executors.Add(new ClearAllVariablesTemplate(item).TransformText());
        this.Instances.Add(new InstanceTemplate(item.GetId()).TransformText());
        this.Edges.Add(new EdgeTemplate("root", item.GetId()).TransformText()); // %%% CONTINUE WITH
    }

    protected override void Visit(ResetVariable item)
    {
        this.Trace(item);

        this.Executors.Add(new ResetVariableTemplate(item).TransformText());
        this.Instances.Add(new InstanceTemplate(item.GetId()).TransformText());
        this.Edges.Add(new EdgeTemplate("root", item.GetId()).TransformText()); // %%% CONTINUE WITH
    }

    protected override void Visit(EditTable item) // %%% TODO
    {
        this.Trace(item);

        //this.ContinueWith(new EditTableExecutor(item, this._workflowState));
    }

    protected override void Visit(EditTableV2 item) // %%% TODO
    {
        this.Trace(item);

        //this.ContinueWith(new EditTableV2Executor(item, this._workflowState));
    }

    protected override void Visit(ParseValue item) // %%% TODO
    {
        this.Trace(item);

        //this.ContinueWith(new ParseValueExecutor(item, this._workflowState));
    }

    protected override void Visit(SendActivity item)
    {
        this.Trace(item);

        this.Executors.Add(new SendActivityTemplate(item).TransformText());
        this.Instances.Add(new InstanceTemplate(item.GetId()).TransformText());
        this.Edges.Add(new EdgeTemplate("root", item.GetId()).TransformText()); // %%% CONTINUE WITH
    }

    protected override void Visit(InvokeAzureAgent item) // %%% TODO
    {
        throw new System.NotImplementedException();
    }

    protected override void Visit(CreateConversation item)
    {
        this.Trace(item);

        this.Executors.Add(new CreateConversationTemplate(item).TransformText());
        this.Instances.Add(new InstanceTemplate(item.GetId()).TransformText());
        this.Edges.Add(new EdgeTemplate("root", item.GetId()).TransformText()); // %%% CONTINUE WITH
    }

    protected override void Visit(AddConversationMessage item)
    {
        this.Trace(item);

        this.Executors.Add(new AddConversationMessageTemplate(item).TransformText());
        this.Instances.Add(new InstanceTemplate(item.GetId()).TransformText());
        this.Edges.Add(new EdgeTemplate("root", item.GetId()).TransformText()); // %%% CONTINUE WITH
    }

    protected override void Visit(CopyConversationMessages item)
    {
        this.Executors.Add(new CopyConversationMessagesTemplate(item).TransformText());
        this.Instances.Add(new InstanceTemplate(item.GetId()).TransformText());
        this.Edges.Add(new EdgeTemplate("root", item.GetId()).TransformText()); // %%% CONTINUE WITH
    }

    protected override void Visit(RetrieveConversationMessage item)
    {
        this.Executors.Add(new RetrieveConversationMessageTemplate(item).TransformText());
        this.Instances.Add(new InstanceTemplate(item.GetId()).TransformText());
        this.Edges.Add(new EdgeTemplate("root", item.GetId()).TransformText()); // %%% CONTINUE WITH
    }

    protected override void Visit(RetrieveConversationMessages item)
    {
        this.Executors.Add(new RetrieveConversationMessagesTemplate(item).TransformText());
        this.Instances.Add(new InstanceTemplate(item.GetId()).TransformText());
        this.Edges.Add(new EdgeTemplate("root", item.GetId()).TransformText()); // %%% CONTINUE WITH
    }

    #region Not supported

    protected override void Visit(AnswerQuestionWithAI item)
    {
        this.NotSupported(item);
    }

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

    //private static string PostId(string actionId) => $"{actionId}_Post";

    //private static string GetParentId(BotElement item) =>
    //    item.GetParentId() ??
    //    throw new DeclarativeModelException($"Missing parent ID for action element: {item.GetId()} [{item.GetType().Name}].");

    //private string ContinuationFor(string parentId) => this.ContinuationFor(parentId, parentId);

    //private string ContinuationFor(string actionId, string parentId)
    //{
    //    actionId = PostId(actionId);
    //    this._workflowModel.AddNode(this.CreateStep(actionId), parentId);
    //    return actionId;
    //}

    //private void RestartAfter(string actionId, string parentId) =>
    //    this._workflowModel.AddNode(this.CreateStep($"{actionId}_Continue"), parentId);

    //private DelegateActionExecutor CreateStep(string actionId, DelegateAction? stepAction = null)
    //{
    //    DelegateActionExecutor stepExecutor = new(actionId, stepAction);

    //    return stepExecutor;
    //}

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
            WorkflowActionVisitor.Steps.Root(parentId);
        }
        Debug.WriteLine($"> VISIT: {FormatItem(item)} => {FormatParent(item)}");
    }

    private static string FormatItem(BotElement element) => $"{element.GetType().Name} ({element.GetId()})";

    private static string FormatParent(BotElement element) =>
        element.Parent is null ?
        throw new DeclarativeModelException($"Undefined parent for {element.GetType().Name} that is member of {element.GetId()}.") :
        $"{element.Parent.GetType().Name} ({element.GetParentId()})";
}
