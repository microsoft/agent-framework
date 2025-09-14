// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Collections.Immutable;
using System.Diagnostics;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.Workflows.Declarative.Extensions;
using Microsoft.Bot.ObjectModel;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Logging.Abstractions;
using Microsoft.PowerFx.Types;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.Workflows.Declarative.Interpreter;

internal abstract class DeclarativeActionExecutor<TAction>(TAction model, DeclarativeWorkflowState state) :
    DeclarativeActionExecutor(model, state)
    where TAction : DialogAction
{
    public new TAction Model => (TAction)base.Model;
}

internal abstract class DeclarativeActionExecutor : Executor<ExecutorResultMessage>
{
    private static readonly ImmutableHashSet<string> s_mutableScopes =
        new HashSet<string>
        {
                VariableScopeNames.Topic,
                VariableScopeNames.Global,
        }.ToImmutableHashSet();

    private string? _parentId;

    protected DeclarativeActionExecutor(DialogAction model, DeclarativeWorkflowState state)
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

    public string ParentId => this._parentId ??= this.Model.GetParentId() ?? WorkflowActionVisitor.Steps.Root();

    internal ILogger Logger { get; set; } = NullLogger<DeclarativeActionExecutor>.Instance;

    protected DeclarativeWorkflowState State { get; }

    protected virtual bool IsDiscreteAction => true;

    protected virtual bool EmitResultEvent => true;

    /// <inheritdoc/>
    public override async ValueTask HandleAsync(ExecutorResultMessage message, IWorkflowContext context)
    {
        if (this.Model.Disabled)
        {
            Debug.WriteLine($"DISABLED {this.GetType().Name} [{this.Id}]");
            return;
        }

        await context.RaiseInvocationEventAsync(this.Model, message.ExecutorId).ConfigureAwait(false);

        Debug.WriteLine($"RESULT #{this.Id} - {message.Result ?? "(null)"}");

        try
        {
            object? result = await this.ExecuteAsync(context, cancellationToken: default).ConfigureAwait(false);

            if (this.EmitResultEvent)
            {
                await context.SendResultMessageAsync(this.Id, result).ConfigureAwait(false);
            }
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
        finally
        {
            if (this.IsDiscreteAction)
            {
                await context.RaiseCompletionEventAsync(this.Model).ConfigureAwait(false);
            }
        }
    }

    protected abstract ValueTask<object?> ExecuteAsync(IWorkflowContext context, CancellationToken cancellationToken = default);

    /// <summary>
    /// Restore the state of the executor from a checkpoint.
    /// This must be overridden to restore any state that was saved during checkpointing.
    /// </summary>
    protected override ValueTask OnCheckpointRestoredAsync(IWorkflowContext context, CancellationToken cancellation = default) =>
        this.State.RestoreAsync(context, cancellation);

    protected async ValueTask AssignAsync(PropertyPath? targetPath, FormulaValue result, IWorkflowContext context)
    {
        if (targetPath is null)
        {
            return;
        }

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
