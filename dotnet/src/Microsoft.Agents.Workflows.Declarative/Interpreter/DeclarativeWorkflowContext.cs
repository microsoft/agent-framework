// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Threading.Tasks;
using Microsoft.Agents.Workflows.Declarative.Extensions;
using Microsoft.Agents.Workflows.Declarative.PowerFx;
using Microsoft.Bot.ObjectModel;
using Microsoft.PowerFx.Types;

namespace Microsoft.Agents.Workflows.Declarative.Interpreter;

internal sealed class DeclarativeWorkflowContext : IWorkflowContext
{
    public DeclarativeWorkflowContext(IWorkflowContext source, WorkflowFormulaState state)
    {
        this.Source = source;
        this.State = state;
    }

    private IWorkflowContext Source { get; }
    public WorkflowFormulaState State { get; }

    /// <inheritdoc/>
    public ValueTask AddEventAsync(WorkflowEvent workflowEvent) => this.Source.AddEventAsync(workflowEvent);

    /// <inheritdoc/>
    public ValueTask QueueClearScopeAsync(string? scopeName = null)
    {
        this.State.ResetAll(scopeName);
        return this.Source.QueueClearScopeAsync(scopeName);
    }

    /// <inheritdoc/>
    public async ValueTask QueueStateUpdateAsync<T>(string key, T? value, string? scopeName = null)
    {
        ValueTask task = value switch
        {
            null => QueueEmptyStateAsync(),
            FormulaValue formulaValue => QueueFormulaStateAsync(formulaValue),
            DataValue dataValue => QueueDataValueStateAsync(dataValue),
            _ => QueueNativeStateAsync(value),
        };

        await task.ConfigureAwait(false);

        ValueTask QueueEmptyStateAsync()
        {
            this.State.Set(key, FormulaValue.NewBlank(), scopeName);
            return this.Source.QueueStateUpdateAsync(key, UnassignedValue.Instance, scopeName);
        }

        ValueTask QueueFormulaStateAsync(FormulaValue formulaValue)
        {
            this.State.Set(key, formulaValue, scopeName);
            return this.Source.QueueStateUpdateAsync(key, formulaValue.ToObject(), scopeName);
        }

        ValueTask QueueDataValueStateAsync(DataValue dataValue)
        {
            FormulaValue formulaValue = dataValue.ToFormula();
            this.State.Set(key, formulaValue, scopeName);
            return this.Source.QueueStateUpdateAsync(key, formulaValue.ToObject(), scopeName);
        }

        ValueTask QueueNativeStateAsync(object? rawValue)
        {
            FormulaValue formulaValue = rawValue.ToFormula();
            this.State.Set(key, formulaValue, scopeName);
            return this.Source.QueueStateUpdateAsync(key, rawValue, scopeName);
        }
    }

    /// <inheritdoc/>
    public ValueTask<T?> ReadStateAsync<T>(string key, string? scopeName = null) => this.Source.ReadStateAsync<T>(key, scopeName);

    /// <inheritdoc/>
    public ValueTask<HashSet<string>> ReadStateKeysAsync(string? scopeName = null) => this.Source.ReadStateKeysAsync(scopeName);

    /// <inheritdoc/>
    public ValueTask SendMessageAsync(object message, string? targetId = null) => this.Source.SendMessageAsync(message, targetId);
}
