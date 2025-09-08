// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Threading.Tasks;
using Microsoft.Agents.Workflows.Declarative.Extensions;
using Microsoft.Agents.Workflows.Declarative.Kit;
using Microsoft.Agents.Workflows.Declarative.PowerFx;
using Microsoft.Bot.ObjectModel;
using Microsoft.PowerFx.Types;

namespace Microsoft.Agents.Workflows.Declarative.Interpreter;

internal sealed class DeclarativeWorkflowContext : IWorkflowContext
{
    public DeclarativeWorkflowContext(IWorkflowContext source, WorkflowScopes? scopes = null)
    {
        this.Source = source;
        this.Scopes = scopes ?? new WorkflowScopes();
        this.IsRestored = scopes is not null;
    }

    private IWorkflowContext Source { get; }
    public WorkflowScopes Scopes { get; } // %%% SCOPE (private)
    public bool IsRestored { get; private set; }

    /// <inheritdoc/>
    public ValueTask AddEventAsync(WorkflowEvent workflowEvent) => this.Source.AddEventAsync(workflowEvent);

    /// <inheritdoc/>
    public ValueTask QueueClearScopeAsync(string? scopeName = null)
    {
        // %%% UPDATE SCOPES
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
            _ => QueueNativeStateAsync(),
        };

        await task.ConfigureAwait(false);

        ValueTask QueueEmptyStateAsync()
        {
            this.Scopes.Set(key, FormulaValue.NewBlank(), scopeName);
            return this.Source.QueueStateUpdateAsync(key, UnassignedValue.Instance, scopeName);
        }

        ValueTask QueueFormulaStateAsync(FormulaValue formulaValue)
        {
            this.Scopes.Set(key, formulaValue, scopeName);
            return this.Source.QueueStateUpdateAsync(key, formulaValue.ToObject(), scopeName);
        }

        ValueTask QueueDataValueStateAsync(DataValue dataValue)
        {
            FormulaValue formulaValue = dataValue.ToFormulaValue();
            this.Scopes.Set(key, formulaValue, scopeName);
            return this.Source.QueueStateUpdateAsync(key, formulaValue.ToObject(), scopeName);
        }

        ValueTask QueueNativeStateAsync()
        {
            // %%% UPDATE SCOPES
            // value.ToFormulaValue();
            return this.Source.QueueStateUpdateAsync(key, value, scopeName);
        }
    }

    /// <inheritdoc/>
    public ValueTask<T?> ReadStateAsync<T>(string key, string? scopeName = null) => this.Source.ReadStateAsync<T>(key, scopeName);

    /// <inheritdoc/>
    public ValueTask<HashSet<string>> ReadStateKeysAsync(string? scopeName = null) => this.Source.ReadStateKeysAsync(scopeName);

    /// <inheritdoc/>
    public ValueTask SendMessageAsync(object message, string? targetId = null) => this.Source.SendMessageAsync(message, targetId);
}
