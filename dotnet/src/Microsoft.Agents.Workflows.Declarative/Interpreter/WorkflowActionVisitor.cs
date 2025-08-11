// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Threading.Tasks;
using Azure.AI.Agents.Persistent;
using Azure.Core.Pipeline;
using Microsoft.Agents.Workflows.Core;
using Microsoft.Agents.Workflows.Declarative.Execution;
using Microsoft.Agents.Workflows.Declarative.Extensions;
using Microsoft.Agents.Workflows.Declarative.Handlers;
using Microsoft.Agents.Workflows.Declarative.PowerFx;
using Microsoft.Bot.ObjectModel;
using Microsoft.PowerFx;
using Microsoft.SemanticKernel.Process.Workflows.Actions;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.Workflows.Declarative.Interpreter;

internal sealed class WorkflowActionVisitor : DialogActionVisitor
{
    private readonly WorkflowBuilder _workflowBuilder;
    private readonly WorkflowModel _workflowModel;
    private readonly WorkflowContext _context;
    private readonly WorkflowScopes _scopes;

    public WorkflowActionVisitor(
        ExecutorIsh rootAction,
        WorkflowContext context,
        WorkflowScopes scopes)
    {
        this._workflowModel = new WorkflowModel(rootAction);
        this._workflowBuilder = new WorkflowBuilder(rootAction);
        this._context = context;
        this._scopes = scopes;
    }

    public Workflow<string> Complete()
    {
        // Process the cached links
        this._workflowModel.ConnectNodes(this._workflowBuilder);

        // Build final workflow
        return this._workflowBuilder.Build<string>();
    }

    protected override void Visit(ActionScope item)
    {
        this.Trace(item, isSkipped: false);

        string parentId = Throw.IfNull(item.GetParentId(), nameof(BotElement.Parent)); // %%% NULL PARENT CASE ???
        if (item.Id.Equals(parentId))
        {
            parentId = $"root_{parentId}";
        }
        this.ContinueWith(this.CreateStep(item.Id.Value, nameof(ActionScope)), parentId);
        //this._workflowBuilder.AddLink(parentId, item.Id.Value); // %%% NEEDED ???
    }

    protected override void Visit(ConditionGroup item)
    {
        this.Trace(item, isSkipped: false);

        //ConditionGroupAction action = new(item);
        //this.ContinueWith(action);
        //this.RestartFrom(item.Id.Value, nameof(ConditionGroupAction), action.ParentId);

        //// %%% SUPPORT: item.ElseActions

        //int index = 1;
        //foreach (ConditionItem conditionItem in item.Conditions)
        //{
        //    // Visit each action in the condition item
        //    conditionItem.Accept(this);

        //    ++index;
        //}
    }

    public override void VisitConditionItem(ConditionItem item)
    {
        this.Trace(item);

        //Func<bool>? condition = null;

        //if (item.Condition is not null)
        //{
        //    // %%% VERIFY IF ONLY ONE CONDITION IS EXPECTED / ALLOWED
        //    condition =
        //        new(() =>
        //        {
        //            RecalcEngine engine = this.CreateEngine();
        //            bool result = engine.Eval(item.Condition.ExpressionText ?? "true").AsBoolean();
        //            Console.WriteLine($"!!! CONDITION: {item.Condition.ExpressionText ?? "true"}={result}");
        //            return result;
        //        });
        //}

        //string stepId = item.Id ?? $"{nameof(ConditionItem)}_{Guid.NewGuid():N}";
        //string parentId = Throw.IfNull(item.GetParentId(), nameof(BotElement.Parent)); // %%% NULL PARENT CASE ???
        //this.ContinueWith(this.CreateStep(stepId, nameof(ConditionItem)), parentId, condition, callback: CompletionHandler);

        //base.VisitConditionItem(item);

        //void CompletionHandler(string _)
        //{
        //    string completionId = ConditionGroupAction.Steps.End(stepId);
        //    this.ContinueWith(this.CreateStep(completionId, $"{nameof(ConditionItem)}_End"), stepId);
        //    this._workflowBuilder.AddLink(completionId, RestartId(parentId));
        //}
    }

    protected override void Visit(GotoAction item)
    {
        this.Trace(item, isSkipped: false);

        string parentId = Throw.IfNull(item.GetParentId(), nameof(BotElement.Parent)); // %%% NULL PARENT CASE ???
        this.ContinueWith(this.CreateStep(item.Id.Value, nameof(GotoAction)), parentId);
        this._workflowModel.AddLink(item.Id.Value, item.ActionId.Value);
        this.RestartFrom(item.Id.Value, nameof(GotoAction), parentId);
    }

    protected override void Visit(Foreach item)
    {
        this.Trace(item, isSkipped: false);

        ForeachAction action = new(item);
        string loopId = ForeachAction.Steps.Next(action.Id);
        this.ContinueWith(action, callback: CompletionHandler);
        string restartId = this.RestartFrom(action);
        this.ContinueWith(this.CreateStep(loopId, $"{nameof(ForeachAction)}_Next", action.TakeNext), action.Id);
        this._workflowModel.AddLink(loopId, restartId, (_) => !action.HasValue);
        this.ContinueWith(this.CreateStep(ForeachAction.Steps.Start(action.Id), $"{nameof(ForeachAction)}_Start"), action.Id, (_) => action.HasValue);
        void CompletionHandler()
        {
            string completionId = ForeachAction.Steps.End(action.Id);
            this.ContinueWith(this.CreateStep(completionId, $"{nameof(ForeachAction)}_End"), action.Id);
            this._workflowModel.AddLink(completionId, loopId);
        }
    }

    protected override void Visit(BreakLoop item) // %%% SUPPORT
    {
        this.Trace(item, isSkipped: false);

        string? loopId = this._workflowModel.LocateParent<ForeachAction>(item.GetParentId());
        if (loopId is not null)
        {
            string parentId = Throw.IfNull(item.GetParentId(), nameof(BotElement.Parent)); // %%% NULL PARENT CASE ???
            this.ContinueWith(this.CreateStep(item.Id.Value, nameof(BreakLoop)), parentId);
            this._workflowModel.AddLink(item.Id.Value, RestartId(loopId));
            this.RestartFrom(item.Id.Value, nameof(BreakLoop), parentId);
        }
    }

    protected override void Visit(ContinueLoop item) // %%% SUPPORT
    {
        this.Trace(item, isSkipped: false);

        string? loopId = this._workflowModel.LocateParent<ForeachAction>(item.GetParentId());
        if (loopId is not null)
        {
            string parentId = Throw.IfNull(item.GetParentId(), nameof(BotElement.Parent)); // %%% NULL PARENT CASE ???
            this.ContinueWith(this.CreateStep(item.Id.Value, nameof(ContinueLoop)), parentId);
            this._workflowModel.AddLink(item.Id.Value, ForeachAction.Steps.Next(loopId));
            this.RestartFrom(item.Id.Value, nameof(ContinueLoop), parentId);
        }
    }

    protected override void Visit(EndConversation item)
    {
        this.Trace(item, isSkipped: false);

        EndConversationAction action = new(item);
        this.ContinueWith(action);
        this.RestartFrom(action);
    }

    protected override void Visit(AnswerQuestionWithAI item)
    {
        this.Trace(item, isSkipped: false);

        this.ContinueWith(new AnswerQuestionWithAIAction(item));
    }

    protected override void Visit(SetVariable item)
    {
        this.Trace(item, isSkipped: false);

        this.ContinueWith(new SetVariableAction(item));
    }

    protected override void Visit(SetTextVariable item)
    {
        this.Trace(item, isSkipped: false);

        this.ContinueWith(new SetTextVariableAction(item));
    }

    protected override void Visit(ClearAllVariables item)
    {
        this.Trace(item, isSkipped: false);

        this.ContinueWith(new ClearAllVariablesAction(item));
    }

    protected override void Visit(ResetVariable item)
    {
        this.Trace(item, isSkipped: false);

        this.ContinueWith(new ResetVariableAction(item));
    }

    protected override void Visit(EditTable item)
    {
        this.Trace(item);
    }

    protected override void Visit(EditTableV2 item)
    {
        this.Trace(item, isSkipped: false);

        this.ContinueWith(new EditTableV2Action(item));
    }

    protected override void Visit(ParseValue item)
    {
        this.Trace(item, isSkipped: false);

        this.ContinueWith(new ParseValueAction(item));
    }

    protected override void Visit(SendActivity item)
    {
        this.Trace(item, isSkipped: false);

        this.ContinueWith(new SendActivityAction(item, this._context.ActivityChannel));
    }

    #region Not supported

    protected override void Visit(DeleteActivity item)
    {
        this.Trace(item);
    }

    protected override void Visit(GetActivityMembers item)
    {
        this.Trace(item);
    }

    protected override void Visit(UpdateActivity item)
    {
        this.Trace(item);
    }

    protected override void Visit(ActivateExternalTrigger item)
    {
        this.Trace(item);
    }

    protected override void Visit(DisableTrigger item)
    {
        this.Trace(item);
    }

    protected override void Visit(WaitForConnectorTrigger item)
    {
        this.Trace(item);
    }

    protected override void Visit(InvokeConnectorAction item)
    {
        this.Trace(item);
    }

    protected override void Visit(InvokeCustomModelAction item)
    {
        this.Trace(item);
    }

    protected override void Visit(InvokeFlowAction item)
    {
        this.Trace(item);
    }

    protected override void Visit(InvokeAIBuilderModelAction item)
    {
        this.Trace(item);
    }

    protected override void Visit(InvokeSkillAction item)
    {
        this.Trace(item);
    }

    protected override void Visit(AdaptiveCardPrompt item)
    {
        this.Trace(item);
    }

    protected override void Visit(Question item)
    {
        this.Trace(item);
    }

    protected override void Visit(CSATQuestion item)
    {
        this.Trace(item);
    }

    protected override void Visit(OAuthInput item)
    {
        this.Trace(item);
    }

    protected override void Visit(BeginDialog item)
    {
        this.Trace(item);
    }

    protected override void Visit(UnknownDialogAction item)
    {
        this.Trace(item);
    }

    protected override void Visit(EndDialog item)
    {
        this.Trace(item);
    }

    protected override void Visit(RepeatDialog item)
    {
        this.Trace(item);
    }

    protected override void Visit(ReplaceDialog item)
    {
        this.Trace(item);
    }

    protected override void Visit(CancelAllDialogs item)
    {
        this.Trace(item);
    }

    protected override void Visit(CancelDialog item)
    {
        this.Trace(item);
    }

    protected override void Visit(EmitEvent item)
    {
        this.Trace(item);
    }

    protected override void Visit(GetConversationMembers item)
    {
        this.Trace(item);
    }

    protected override void Visit(HttpRequestAction item)
    {
        this.Trace(item);
    }

    protected override void Visit(RecognizeIntent item)
    {
        this.Trace(item);
    }

    protected override void Visit(TransferConversation item)
    {
        this.Trace(item);
    }

    protected override void Visit(TransferConversationV2 item)
    {
        this.Trace(item);
    }

    protected override void Visit(SignOutUser item)
    {
        this.Trace(item);
    }

    protected override void Visit(LogCustomTelemetryEvent item)
    {
        this.Trace(item);
    }

    protected override void Visit(DisconnectedNodeContainer item)
    {
        this.Trace(item);
    }

    protected override void Visit(CreateSearchQuery item)
    {
        this.Trace(item);
    }

    protected override void Visit(SearchKnowledgeSources item)
    {
        this.Trace(item);
    }

    protected override void Visit(SearchAndSummarizeWithCustomModel item)
    {
        this.Trace(item);
    }

    protected override void Visit(SearchAndSummarizeContent item)
    {
        this.Trace(item);
    }

    #endregion

    private void ContinueWith(
        ProcessAction action,
        Func<object?, bool>? condition = null,
        ScopeCompletionHandler? callback = null) =>
        this.ContinueWith(this.DefineActionExecutor(action), action.ParentId, condition, action.GetType(), callback);

    private void ContinueWith(
        ExecutorIsh executor,
        string parentId,
        Func<object?, bool>? condition = null,
        Type? actionType = null,
        ScopeCompletionHandler? callback = null)
    {
        this._workflowModel.AddNode(executor, parentId, actionType, callback);
        this._workflowModel.AddLinkFromPeer(parentId, executor.Id, condition);
    }

    private static string RestartId(string actionId) => $"post_{actionId}";

    private string RestartFrom(ProcessAction action) =>
        this.RestartFrom(action.Id, action.GetType().Name, action.ParentId);

    private string RestartFrom(string actionId, string name, string parentId)
    {
        string restartId = RestartId(actionId);
        this._workflowModel.AddNode(this.CreateStep(restartId, $"{name}_Restart"), parentId);
        return restartId;
    }

    private ExecutorIsh CreateStep(string actionId, string name, Action<ProcessActionContext>? stepAction = null)
    {
        DeclarativeActionExecutor stepExecutor =
            new(actionId,
                () =>
                {
                    Console.WriteLine($"!!! STEP {name} [{actionId}]"); // %%% REMOVE
                    stepAction?.Invoke(this.CreateActionContext(actionId));
                    return new ValueTask();
                });

        //this._workflowBuilder.BindExecutor(stepExecutor);

        return stepExecutor;
    }

    // This implementation accepts the context as a parameter in order to pin the context closure.
    // The step cannot reference this.CurrentContext directly, as this will always be the final context.
    private ExecutorIsh DefineActionExecutor(ProcessAction action)
    {
        DeclarativeActionExecutor stepExecutor =
            new(action.Id,
                async () =>
                {
                    Console.WriteLine($"!!! STEP {action.GetType().Name} [{action.Id}]"); // %%% REMOVE

                    if (action.Model.Disabled) // %%% VALIDATE
                    {
                        Console.WriteLine($"!!! DISABLED {action.GetType().Name} [{action.Id}]"); // %%% REMOVE
                        return;
                    }

                    try
                    {
                        await action.ExecuteAsync(
                            this.CreateActionContext(action.Id),
                            cancellationToken: default).ConfigureAwait(false); // %%% CANCELTOKEN
                    }
                    catch (ProcessActionException)
                    {
                        Console.WriteLine($"*** STEP [{action.Id}] ERROR - Action failure"); // %%% LOGGER
                        throw;
                    }
                    catch (Exception exception)
                    {
                        Console.WriteLine($"*** STEP [{action.Id}] ERROR - {exception.GetType().Name}\n{exception.Message}"); // %%% LOGGER
                        throw;
                    }
                });

        //this._workflowBuilder.BindExecutor(stepExecutor);

        return stepExecutor;
    }

    private ProcessActionContext CreateActionContext(string actionId) => new(this.CreateEngine(), this._scopes, this.CreateClient, this._context.LoggerFactory.CreateLogger(actionId));

    private PersistentAgentsClient CreateClient()
    {
        PersistentAgentsAdministrationClientOptions clientOptions = new();

        if (this._context.HttpClient is not null)
        {
            clientOptions.Transport = new HttpClientTransport(this._context.HttpClient);
            //clientOptions.RetryPolicy = new RetryPolicy(maxRetries: 0);
        }

        return new PersistentAgentsClient(this._context.ProjectEndpoint, this._context.ProjectCredentials, clientOptions);
    }

    private RecalcEngine CreateEngine() => RecalcEngineFactory.Create(this._scopes, this._context.MaximumExpressionLength);

    private void Trace(BotElement item)
    {
        Console.WriteLine($"> VISIT: {new string('\t', this._workflowModel.GetDepth(item.GetParentId()))}{FormatItem(item)} => {FormatParent(item)}"); // %%% LOGGER
    }

    private void Trace(DialogAction item, bool isSkipped = true)
    {
        string? parentId = item.GetParentId();
        if (item.Id.Equals(parentId ?? string.Empty))
        {
            parentId = $"root_{parentId}";
        }
        Console.WriteLine($"> {(isSkipped ? "EMPTY" : "VISIT")}: {new string('\t', this._workflowModel.GetDepth(parentId))}{FormatItem(item)} => {FormatParent(item)}"); // %%% LOGGER
    }

    private static string FormatItem(BotElement element) => $"{element.GetType().Name} ({element.GetId()})";

    private static string FormatParent(BotElement element) =>
        element.Parent is null ?
        throw new InvalidActionException($"Undefined parent for {element.GetType().Name} that is member of {element.GetId()}.") :
        $"{element.Parent.GetType().Name} ({element.GetParentId()})";
}
