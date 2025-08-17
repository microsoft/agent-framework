// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Diagnostics;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.Workflows.Declarative.ObjectModel;
using Microsoft.Agents.Workflows.Declarative.Extensions;
using Microsoft.Agents.Workflows.Declarative.PowerFx;
using Microsoft.Agents.Workflows.Reflection;
using Microsoft.Bot.ObjectModel;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Logging.Abstractions;
using Microsoft.PowerFx.Types;

namespace Microsoft.Agents.Workflows.Declarative.Interpreter;

internal sealed record class ExecutionResultMessage(string ExecutorId, object? Result = null);

internal abstract class DeclarativeActionExecutor<TAction>(TAction model) :
    WorkflowActionExecutor(model)
    where TAction : DialogAction
{
    public new TAction Model => (TAction)base.Model;
}

internal abstract class WorkflowActionExecutor :
    ReflectingExecutor<WorkflowActionExecutor>,
    IMessageHandler<ExecutionResultMessage>
{
    public const string RootActionId = "(root)";

    private string? _parentId;
    private WorkflowExecutionContext? _context;

    protected WorkflowActionExecutor(DialogAction model)
        : base(model.Id.Value)
    {
        if (!model.HasRequiredProperties)
        {
            throw new WorkflowModelException($"Missing required properties for element: {model.GetId()} ({model.GetType().Name}).");
        }

        this.Model = model;
    }

    public DialogAction Model { get; }

    public string ParentId => this._parentId ??= this.Model.GetParentId() ?? RootActionId;

    internal ILogger Logger { get; set; } = NullLogger<WorkflowActionExecutor>.Instance;

    internal DeclarativeWorkflowContext WorkflowContext { get; set; } = DeclarativeWorkflowContext.Default; // %%% HAXX: Initial state

    protected WorkflowExecutionContext Context =>
        this._context ??
        throw new WorkflowExecutionException("Context not assigned");

    private void Attach(WorkflowExecutionContext executionContext) // %%% IMPROVE ???
    {
        this._context = executionContext;
    }

    /// <inheritdoc/>
    public async ValueTask HandleAsync(ExecutionResultMessage message, IWorkflowContext context)
    {
        if (this.Model.Disabled)
        {
            Debug.WriteLine($"!!! DISABLED {this.GetType().Name} [{this.Id}]");
            return;
        }

        WorkflowScopes scopes = await context.GetScopesAsync(default).ConfigureAwait(false);
        WorkflowExecutionContext executionContext = this.WorkflowContext.CreateActionContext(this.Id, scopes); // %%% IMPROVE ???
        this.Attach(executionContext); // %%% REMOVE

        try
        {
            await this.ExecuteAsync(context, cancellationToken: default).ConfigureAwait(false);

            await context.SetScopesAsync(scopes, default).ConfigureAwait(false);
            await context.SendMessageAsync(new ExecutionResultMessage(this.Id, executionContext.Result)).ConfigureAwait(false);
        }
        catch (WorkflowExecutionException)
        {
            Debug.WriteLine($"*** STEP [{this.Id}] ERROR - Action failure");
            throw;
        }
        catch (Exception exception)
        {
            Debug.WriteLine($"*** STEP [{this.Id}] ERROR - {exception.GetType().Name}\n{exception.Message}");
            throw new WorkflowExecutionException($"Unhandled workflow failure - #{this.Id} ({this.Model.GetType().Name})", exception);
        }
    }

    protected abstract ValueTask ExecuteAsync(IWorkflowContext context, CancellationToken cancellationToken = default);

    protected void AssignTarget(WorkflowExecutionContext context, PropertyPath targetPath, FormulaValue result)
    {
        context.Engine.SetScopedVariable(context.Scopes, targetPath, result);
#if DEBUG
        string? resultValue = result.Format();
        string valuePosition = (resultValue?.IndexOf('\n') ?? -1) >= 0 ? Environment.NewLine : " ";
        Debug.WriteLine(
            $"""
            !!! ASSIGN {this.GetType().Name} [{this.Id}]
                NAME: {targetPath.Format()}
                VALUE:{valuePosition}{result.Format()} ({result.GetType().Name})
            """);
#endif
    }
}
