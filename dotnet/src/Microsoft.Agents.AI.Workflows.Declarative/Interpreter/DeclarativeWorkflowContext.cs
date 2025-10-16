// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Frozen;
using System.Collections.Generic;
using System.Diagnostics;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Workflows.Declarative.Extensions;
using Microsoft.Agents.AI.Workflows.Declarative.Kit;
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
    public IReadOnlyDictionary<string, string>? TraceContext => this.Source.TraceContext;

    /// <inheritdoc/>
    public bool ConcurrentRunsEnabled => this.Source.ConcurrentRunsEnabled;

    /// <inheritdoc/>
    public ValueTask AddEventAsync(WorkflowEvent workflowEvent, CancellationToken cancellationToken = default)
        => this.Source.AddEventAsync(workflowEvent, cancellationToken);

    /// <inheritdoc/>
    public ValueTask YieldOutputAsync(object output, CancellationToken cancellationToken = default)
        => this.Source.YieldOutputAsync(output, cancellationToken);

    /// <inheritdoc/>
    public ValueTask RequestHaltAsync() => this.Source.RequestHaltAsync();

    /// <inheritdoc/>
    public async ValueTask QueueClearScopeAsync(string? scopeName = null, CancellationToken cancellationToken = default)
    {
        if (scopeName is not null)
        {
            if (ManagedScopes.Contains(scopeName))
            {
                // Copy keys to array to avoid modifying collection during enumeration.
                foreach (string key in this.State.Keys(scopeName).ToArray())
                {
                    await this.UpdateStateAsync(key, UnassignedValue.Instance, scopeName, allowSystem: false, cancellationToken).ConfigureAwait(false);
                }
            }
            else
            {
                await this.Source.QueueClearScopeAsync(scopeName, cancellationToken).ConfigureAwait(false);
            }

            this.State.Bind();
        }
    }

    /// <inheritdoc/>
    public async ValueTask QueueStateUpdateAsync<T>(string key, T? value, string? scopeName = null, CancellationToken cancellationToken = default)
    {
        await this.UpdateStateAsync(key, value, scopeName, allowSystem: false, cancellationToken).ConfigureAwait(false);
        this.State.Bind();
    }

    private bool IsManagedScope(string? scopeName) => scopeName is not null && VariableScopeNames.IsValidName(scopeName);

    /// <inheritdoc/>
    public async ValueTask<TValue?> ReadStateAsync<TValue>(string key, string? scopeName = null, CancellationToken cancellationToken = default)
    {
        return typeof(TValue) switch
        {
            // Not a managed scope, just pass through.  This is valid when a declarative
            // workflow has been ejected to code (where DeclarativeWorkflowContext is also utilized).
            _ when !this.IsManagedScope(scopeName) => await this.Source.ReadStateAsync<TValue>(key, scopeName, cancellationToken).ConfigureAwait(false),
            // Retrieve formula values directly from the managed state to avoid conversion.
            _ when typeof(TValue) == typeof(FormulaValue) => (TValue?)(object?)this.State.Get(key, scopeName),
            // Retrieve native types from the source context to avoid conversion.
            _ => await this.Source.ReadStateAsync<TValue>(key, scopeName, cancellationToken).ConfigureAwait(false),
        };
    }

    public async ValueTask<TValue> ReadOrInitStateAsync<TValue>(string key, Func<TValue> initialStateFactory, string? scopeName = null, CancellationToken cancellationToken = default)
    {
        return typeof(TValue) switch
        {
            // Not a managed scope, just pass through.  This is valid when a declarative
            // workflow has been ejected to code (where DeclarativeWorkflowContext is also utilized).
            _ when !this.IsManagedScope(scopeName) => await this.Source.ReadOrInitStateAsync(key, initialStateFactory, scopeName, cancellationToken).ConfigureAwait(false),
            // Retrieve formula values directly from the managed state to avoid conversion.
            _ when typeof(TValue) == typeof(FormulaValue) => await EnsureFormulaValueAsync().ConfigureAwait(false),
            // Retrieve native types from the source context to avoid conversion.
            _ => await this.Source.ReadOrInitStateAsync(key, initialStateFactory, scopeName, cancellationToken).ConfigureAwait(false),
        };

        async ValueTask<TValue> EnsureFormulaValueAsync()
        {
            Debug.Assert(typeof(TValue) == typeof(FormulaValue), "It is a bug to call this method with TValue not === FormulaValue");
            FormulaValue? result = this.State.Get(key, scopeName);

            if (result is null or BlankValue)
            {
                result = initialStateFactory() as FormulaValue;
                if (result is null)
                {
                    throw new InvalidOperationException($"The initial state factory for key '{key}' in scope '{scopeName}' did not return a FormulaValue.");
                }

                this.State.Set(key, result, scopeName);
                await this.Source.QueueStateUpdateAsync(key, result.AsPortable(), scopeName, cancellationToken)
                                 .ConfigureAwait(false);
            }

            return (TValue)(object)result!; // The null analyzer is confused here, but it is impossible to hit this line with result is null
        }
    }

    /// <inheritdoc/>
    public ValueTask<HashSet<string>> ReadStateKeysAsync(string? scopeName = null, CancellationToken cancellationToken = default)
        => this.Source.ReadStateKeysAsync(scopeName, cancellationToken);

    /// <inheritdoc/>
    public ValueTask SendMessageAsync(object message, string? targetId = null, CancellationToken cancellationToken = default)
        => this.Source.SendMessageAsync(message, targetId, cancellationToken);

    public ValueTask UpdateStateAsync<T>(string key, T? value, string? scopeName, bool allowSystem, CancellationToken cancellationToken = default)
    {
        bool isManagedScope =
            scopeName is not null && // null scope cannot be managed
            VariableScopeNames.IsValidName(scopeName);

        if (!isManagedScope)
        {
            // Not a managed scope, just pass through.  This is valid when a declarative
            // workflow has been ejected to code (where DeclarativeWorkflowContext is also utilized).
            return this.Source.QueueStateUpdateAsync(key, value, scopeName, cancellationToken);
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
            return this.Source.QueueStateUpdateAsync(key, UnassignedValue.Instance, scopeName, cancellationToken);
        }

        ValueTask QueueFormulaStateAsync(FormulaValue formulaValue)
        {
            if (isManagedScope)
            {
                this.State.Set(key, formulaValue, scopeName);
            }

            return this.Source.QueueStateUpdateAsync(key, formulaValue.AsPortable(), scopeName, cancellationToken);
        }

        ValueTask QueueDataValueStateAsync(DataValue dataValue)
        {
            FormulaValue formulaValue = dataValue.ToFormula();

            if (isManagedScope)
            {
                this.State.Set(key, formulaValue, scopeName);
            }

            return this.Source.QueueStateUpdateAsync(key, formulaValue.AsPortable(), scopeName, cancellationToken);
        }

        ValueTask QueueNativeStateAsync(object rawValue)
        {
            FormulaValue formulaValue = rawValue.ToFormula();

            if (isManagedScope)
            {
                this.State.Set(key, formulaValue, scopeName);
            }

            return this.Source.QueueStateUpdateAsync(key, formulaValue.AsPortable(), scopeName, cancellationToken);
        }
    }
}
