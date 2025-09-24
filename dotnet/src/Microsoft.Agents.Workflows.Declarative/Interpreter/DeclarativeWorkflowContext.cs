// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Frozen;
using System.Collections.Generic;
using System.Linq;
using System.Threading.Tasks;
using Microsoft.Agents.Workflows.Declarative.Extensions;
using Microsoft.Agents.Workflows.Declarative.PowerFx;
using Microsoft.Bot.ObjectModel;
using Microsoft.PowerFx.Types;

namespace Microsoft.Agents.Workflows.Declarative.Interpreter;

internal sealed class DeclarativeWorkflowContext : IWorkflowContext
{
    public static readonly FrozenSet<string> ManagedScopes =
        [
            VariableScopeNames.Topic,
            VariableScopeNames.Global,
        ];

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
    public async ValueTask QueueClearScopeAsync(string? scopeName = null)
    {
        if (scopeName is not null)
        {
            if (ManagedScopes.Contains(scopeName))
            {
                // Copy keys to array to avoid modifying collection during enumeration.
                foreach (string key in this.State.Keys(scopeName).ToArray())
                {
                    await this.UpdateStateAsync(key, UnassignedValue.Instance, scopeName).ConfigureAwait(false);
                }
            }
            else
            {
                await this.Source.QueueClearScopeAsync(scopeName).ConfigureAwait(false);
            }

            this.State.Bind();
        }
    }

    /// <inheritdoc/>
    public async ValueTask QueueStateUpdateAsync<T>(string key, T? value, string? scopeName = null)
    {
        await this.UpdateStateAsync(key, value, scopeName).ConfigureAwait(false);
        this.State.Bind();
    }

    public async ValueTask QueueSystemUpdateAsync<TValue>(string key, TValue? value)
    {
        await this.UpdateStateAsync(key, value, VariableScopeNames.System, allowSystem: true).ConfigureAwait(false);
        this.State.Bind();
    }

    /// <inheritdoc/>
    public ValueTask<T?> ReadStateAsync<T>(string key, string? scopeName = null) => this.Source.ReadStateAsync<T>(key, scopeName);

    /// <inheritdoc/>
    public ValueTask<HashSet<string>> ReadStateKeysAsync(string? scopeName = null) => this.Source.ReadStateKeysAsync(scopeName);

    /// <inheritdoc/>
    public ValueTask SendMessageAsync(object message, string? targetId = null) => this.Source.SendMessageAsync(message, targetId);

    private ValueTask UpdateStateAsync<T>(string key, T? value, string? scopeName, bool allowSystem = true)
    {
        bool isManagedScope =
            scopeName != null && // null scope cannot be managed
            (ManagedScopes.Contains(scopeName) ||
            (allowSystem && VariableScopeNames.System.Equals(scopeName, StringComparison.Ordinal)));

        if (!isManagedScope)
        {
            // Not a managed scope, just pass through.  This is valid when a declarative
            // workflow has been ejected to code (where DeclarativeWorkflowContext is also utilized).
            return this.Source.QueueStateUpdateAsync(key, value, scopeName);
        }

        return value switch
        {
            null => QueueEmptyStateAsync(),
            UnassignedValue => QueueEmptyStateAsync(),
            BlankValue => QueueEmptyStateAsync(),
            FormulaValue formulaValue => QueueFormulaStateAsync(formulaValue),
            DataValue dataValue => QueueDataValueStateAsync(dataValue),
            _ => QueueNativeStateAsync(value),
        };

        ValueTask QueueEmptyStateAsync()
        {
            if (isManagedScope)
            {
                this.State.Set(key, FormulaValue.NewBlank(), scopeName);
            }
            return this.Source.QueueStateUpdateAsync(key, UnassignedValue.Instance, scopeName);
        }

        ValueTask QueueFormulaStateAsync(FormulaValue formulaValue)
        {
            if (isManagedScope)
            {
                this.State.Set(key, formulaValue, scopeName);
            }
            return this.Source.QueueStateUpdateAsync(key, formulaValue.ToObject(), scopeName);
        }

        ValueTask QueueDataValueStateAsync(DataValue dataValue)
        {
            FormulaValue formulaValue = dataValue.ToFormula();
            if (isManagedScope)
            {
                this.State.Set(key, formulaValue, scopeName);
            }
            return this.Source.QueueStateUpdateAsync(key, formulaValue.ToObject(), scopeName);
        }

        ValueTask QueueNativeStateAsync(object? rawValue)
        {
            FormulaValue formulaValue = rawValue.ToFormula();
            if (isManagedScope)
            {
                this.State.Set(key, formulaValue, scopeName);
            }
            return this.Source.QueueStateUpdateAsync(key, rawValue, scopeName);
        }
    }
}
