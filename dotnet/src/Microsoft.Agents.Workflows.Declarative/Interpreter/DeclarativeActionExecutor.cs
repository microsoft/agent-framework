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
    private DeclarativeWorkflowState? _state;

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

    internal DeclarativeWorkflowOptions Options { get; set; } = DeclarativeWorkflowOptions.Default;

    protected DeclarativeWorkflowState State
    {
        get => this._state ?? throw new WorkflowExecutionException("Context not assigned");
        private set { this._state = value; }
    }

    /// <inheritdoc/>
    public async ValueTask HandleAsync(ExecutionResultMessage message, IWorkflowContext context)
    {
        if (this.Model.Disabled)
        {
            Debug.WriteLine($"!!! DISABLED {this.GetType().Name} [{this.Id}]");
            return;
        }

        WorkflowScopes scopes = await context.GetScopedStateAsync(default).ConfigureAwait(false);
        this.State = new DeclarativeWorkflowState(this.Options.CreateRecalcEngine(), scopes);

        try
        {
            object? result = await this.ExecuteAsync(context, cancellationToken: default).ConfigureAwait(false);

            await context.SetScopedStateAsync(scopes, default).ConfigureAwait(false);
            await context.SendMessageAsync(new ExecutionResultMessage(this.Id, result)).ConfigureAwait(false);
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

    protected abstract ValueTask<object?> ExecuteAsync(IWorkflowContext context, CancellationToken cancellationToken = default);

    protected void AssignTarget(PropertyPath targetPath, FormulaValue result)
    {
        this.State.Set(targetPath, result);
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
