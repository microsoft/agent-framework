// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Collections.Immutable;
using System.Diagnostics;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.Workflows.Declarative.Extensions;
using Microsoft.Agents.Workflows.Reflection;
using Microsoft.Bot.ObjectModel;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Logging.Abstractions;
using Microsoft.PowerFx.Types;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.Workflows.Declarative.Interpreter;

internal sealed record class DeclarativeExecutorResult(string ExecutorId, object? Result = null);

internal abstract class DeclarativeActionExecutor<TAction>(TAction model, DeclarativeWorkflowState state) :
    WorkflowActionExecutor(model, state)
    where TAction : DialogAction
{
    public new TAction Model => (TAction)base.Model;
}

internal abstract class WorkflowActionExecutor :
    ReflectingExecutor<WorkflowActionExecutor>,
    IMessageHandler<DeclarativeExecutorResult>
{
    public const string RootActionId = "(root)";

    private static readonly ImmutableHashSet<string> s_mutableScopes =
        new HashSet<string>
        {
                VariableScopeNames.Topic,
                VariableScopeNames.Global,
        }.ToImmutableHashSet();

    private string? _parentId;

    protected WorkflowActionExecutor(DialogAction model, DeclarativeWorkflowState state)
        : base(model.Id.Value)
    {
        if (!model.HasRequiredProperties)
        {
            throw new DeclarativeModelException($"Missing required properties for element: {model.GetId()} ({model.GetType().Name}).");
        }

        this.Model = model;
        this.State = state;
    }

    public DialogAction Model { get; }

    public string ParentId => this._parentId ??= this.Model.GetParentId() ?? RootActionId;

    internal ILogger Logger { get; set; } = NullLogger<WorkflowActionExecutor>.Instance;

    protected DeclarativeWorkflowState State { get; }

    /// <inheritdoc/>
    public async ValueTask HandleAsync(DeclarativeExecutorResult message, IWorkflowContext context)
    {
        if (this.Model.Disabled)
        {
            Debug.WriteLine($"DISABLED {this.GetType().Name} [{this.Id}]");
            return;
        }

        await this.State.RestoreAsync(context, default).ConfigureAwait(false);

        try
        {
            object? result = await this.ExecuteAsync(context, cancellationToken: default).ConfigureAwait(false);

            await context.SendMessageAsync(new DeclarativeExecutorResult(this.Id, result)).ConfigureAwait(false);
        }
        catch (DeclarativeActionException exception)
        {
            Debug.WriteLine($"ERROR [{this.Id}] {exception.GetType().Name}\n{exception.Message}");
            throw;
        }
        catch (Exception exception)
        {
            Debug.WriteLine($"ERROR [{this.Id}] {exception.GetType().Name}\n{exception.Message}");
            throw new DeclarativeActionException($"Unhandled workflow failure - #{this.Id} ({this.Model.GetType().Name})", exception);
        }
    }

    protected abstract ValueTask<object?> ExecuteAsync(IWorkflowContext context, CancellationToken cancellationToken = default);

    protected async ValueTask AssignAsync(PropertyPath targetPath, FormulaValue result, IWorkflowContext context)
    {
        if (!s_mutableScopes.Contains(Throw.IfNull(targetPath.VariableScopeName)))
        {
            throw new DeclarativeModelException($"Invalid scope: {targetPath.VariableScopeName}");
        }

        await this.State.SetAsync(targetPath, result, context).ConfigureAwait(false);

#if DEBUG
        string? resultValue = result.Format();
        string valuePosition = (resultValue?.IndexOf('\n') ?? -1) >= 0 ? Environment.NewLine : " ";
        Debug.WriteLine(
            $"""
            STATE: {this.GetType().Name} [{this.Id}]
             NAME: {targetPath.Format()}
            VALUE:{valuePosition}{result.Format()} ({result.GetType().Name})
            """);
#endif
    }

    protected DeclarativeActionException Exception(string text, Exception? exception = null)
    {
        string message = $"Unexpected workflow failure during {this.Model.GetType().Name} [{this.Id}]: {text}";
        return exception is null ? new(message) : new(message, exception);
    }
}
