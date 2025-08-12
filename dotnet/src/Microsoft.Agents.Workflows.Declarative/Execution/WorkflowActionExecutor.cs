// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Diagnostics;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.Workflows.Core;
using Microsoft.Agents.Workflows.Declarative.Extensions;
using Microsoft.Agents.Workflows.Declarative.PowerFx;
using Microsoft.Bot.ObjectModel;
using Microsoft.Extensions.Logging;
using Microsoft.PowerFx.Types;

namespace Microsoft.Agents.Workflows.Declarative.Execution;

internal abstract class WorkflowActionExecutor<TAction>(TAction model) :
    WorkflowActionExecutor(model)
    where TAction : DialogAction
{
    public new TAction Model => (TAction)base.Model;
}

internal abstract class WorkflowActionExecutor(DialogAction model) :
    Executor<WorkflowActionExecutor>(model.Id.Value),
    IMessageHandler<string>
{
    public const string RootActionId = "(root)";

    private string? _parentId;
    private WorkflowExecutionContext? _context;

    public string ParentId => this._parentId ??= this.Model.GetParentId() ?? RootActionId;

    public DialogAction Model { get; } = model;

    protected WorkflowExecutionContext Context =>
        this._context ??
        throw new WorkflowExecutionException("Context not assigned");

    internal void Attach(WorkflowExecutionContext executionContext)
    {
        this._context = executionContext;
    }

    /// <inheritdoc/>
    public async ValueTask HandleAsync(string message, IWorkflowContext context)
    {
        if (this.Model.Disabled)
        {
            Debug.WriteLine($"!!! DISABLED {this.GetType().Name} [{this.Id}]");
            return;
        }

        try
        {
            await this.ExecuteAsync(cancellationToken: default).ConfigureAwait(false);

            await context.SendMessageAsync($"{this.Id}: {DateTime.UtcNow.ToShortTimeString()}").ConfigureAwait(false);
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

    protected abstract ValueTask ExecuteAsync(CancellationToken cancellationToken = default);

    protected void AssignTarget(WorkflowExecutionContext context, PropertyPath targetPath, FormulaValue result)
    {
        context.Engine.SetScopedVariable(context.Scopes, targetPath, result);
        string? resultValue = result.Format();
        string valuePosition = (resultValue?.IndexOf('\n') ?? -1) >= 0 ? Environment.NewLine : " ";
        Debug.WriteLine(
            $"""
            !!! ASSIGN {this.GetType().Name} [{this.Id}]
                NAME: {targetPath.Format()}
                VALUE:{valuePosition}{result.Format()} ({result.GetType().Name})
            """);
    }
}
