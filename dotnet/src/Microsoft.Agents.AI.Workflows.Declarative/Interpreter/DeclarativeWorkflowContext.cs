﻿// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Frozen;
using System.Collections.Generic;
using System.Linq;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Workflows.Declarative.Extensions;
using Microsoft.Agents.AI.Workflows.Declarative.PowerFx;
using Microsoft.Bot.ObjectModel;
using Microsoft.PowerFx.Types;

namespace Microsoft.Agents.AI.Workflows.Declarative.Interpreter;

internal sealed class DeclarativeWorkflowContext : IWorkflowContext
{
    public static readonly FrozenSet<string> ManagedScopes =
        [
            VariableScopeNames.Local,
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
    public ValueTask YieldOutputAsync(object output) => this.Source.YieldOutputAsync(output);

    /// <inheritdoc/>
    public ValueTask RequestHaltAsync() => this.Source.RequestHaltAsync();

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
    public async ValueTask<TValue?> ReadStateAsync<TValue>(string key, string? scopeName = null)
    {
        bool isManagedScope =
            scopeName is not null && // null scope cannot be managed
            VariableScopeNames.IsValidName(scopeName);

        return typeof(TValue) switch
        {
            // Not a managed scope, just pass through.  This is valid when a declarative
            // workflow has been ejected to code (where DeclarativeWorkflowContext is also utilized).
            _ when !isManagedScope => await this.Source.ReadStateAsync<TValue>(key, scopeName).ConfigureAwait(false),
            // Retrieve formula values directly from the managed state to avoid conversion.
            _ when typeof(TValue) == typeof(FormulaValue) => (TValue?)(object?)this.State.Get(key, scopeName),
            // Retrieve native types from the source context to avoid conversion.
            _ => await this.Source.ReadStateAsync<TValue>(key, scopeName).ConfigureAwait(false),
        };
    }

    /// <inheritdoc/>
    public ValueTask<HashSet<string>> ReadStateKeysAsync(string? scopeName = null) => this.Source.ReadStateKeysAsync(scopeName);

    /// <inheritdoc/>
    public ValueTask SendMessageAsync(object message, string? targetId = null) => this.Source.SendMessageAsync(message, targetId);

    private ValueTask UpdateStateAsync<T>(string key, T? value, string? scopeName, bool allowSystem = true)
    {
        bool isManagedScope =
            scopeName is not null && // null scope cannot be managed
            VariableScopeNames.IsValidName(scopeName);

        if (!isManagedScope)
        {
            // Not a managed scope, just pass through.  This is valid when a declarative
            // workflow has been ejected to code (where DeclarativeWorkflowContext is also utilized).
            return this.Source.QueueStateUpdateAsync(key, value, scopeName);
        }

        if (!ManagedScopes.Contains(scopeName!) && !allowSystem)
        {
            throw new DeclarativeActionException($"Cannot manage variable definitions in scope: '{scopeName}'.");
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
            if (isManagedScope)
            {
                FormulaValue formulaValue = dataValue.ToFormula();
                this.State.Set(key, formulaValue, scopeName);
            }
            return this.Source.QueueStateUpdateAsync(key, dataValue.ToObject(), scopeName);
        }

        ValueTask QueueNativeStateAsync(object? rawValue)
        {
            if (isManagedScope)
            {
                FormulaValue formulaValue = rawValue.ToFormula();
                this.State.Set(key, formulaValue, scopeName);
            }
            return this.Source.QueueStateUpdateAsync(key, rawValue, scopeName);
        }
    }
}
