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
using Microsoft.Agents.ObjectModel;
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
                    await this.UpdateStateAsync(key, UnassignedValue.Instance, scopeName, allowSystem: false, cancellationToken: cancellationToken).ConfigureAwait(false);
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
        await this.UpdateStateAsync(key, value, scopeName, allowSystem: false, cancellationToken: cancellationToken).ConfigureAwait(false);
        this.State.Bind();
    }

    internal async ValueTask QueueStateUpdateAsync<T>(
        string key,
        T? value,
        string? scopeName,
        SensitivityLevel sensitivity,
        CancellationToken cancellationToken = default)
    {
        await this.UpdateStateAsync(key, value, scopeName, allowSystem: false, sensitivity: sensitivity, cancellationToken: cancellationToken).ConfigureAwait(false);
        this.State.Bind();
    }

    private static bool IsManagedScope(string? scopeName) => scopeName is not null && VariableScopeNames.IsValidName(scopeName);

    /// <inheritdoc/>
    public async ValueTask<TValue?> ReadStateAsync<TValue>(string key, string? scopeName = null, CancellationToken cancellationToken = default)
    {
        scopeName = IsManagedScope(scopeName) ? WorkflowFormulaState.GetScopeName(scopeName) : scopeName;

        return typeof(TValue) switch
        {
            // Not a managed scope, just pass through.  This is valid when a declarative
            // workflow has been ejected to code (where DeclarativeWorkflowContext is also utilized).
            _ when !IsManagedScope(scopeName) => await this.Source.ReadStateAsync<TValue>(key, scopeName, cancellationToken).ConfigureAwait(false),
            // Retrieve formula values directly from the managed state to avoid conversion.
            _ when typeof(TValue) == typeof(FormulaValue) => (TValue?)(object?)this.State.Get(key, scopeName),
            // Retrieve native types from the source context to avoid conversion.
            _ => await this.Source.ReadStateAsync<TValue>(key, scopeName, cancellationToken).ConfigureAwait(false),
        };
    }

    public async ValueTask<TValue> ReadOrInitStateAsync<TValue>(string key, Func<TValue> initialStateFactory, string? scopeName = null, CancellationToken cancellationToken = default)
    {
        scopeName = IsManagedScope(scopeName) ? WorkflowFormulaState.GetScopeName(scopeName) : scopeName;

        return typeof(TValue) switch
        {
            // Not a managed scope, just pass through.  This is valid when a declarative
            // workflow has been ejected to code (where DeclarativeWorkflowContext is also utilized).
            _ when !IsManagedScope(scopeName) => await this.Source.ReadOrInitStateAsync(key, initialStateFactory, scopeName, cancellationToken).ConfigureAwait(false),
            // Retrieve formula values directly from the managed state to avoid conversion.
            _ when typeof(TValue) == typeof(FormulaValue) => await EnsureFormulaValueAsync().ConfigureAwait(false),
            // Retrieve native types from the source context to avoid conversion.
            _ => await EnsureNativeValueAsync().ConfigureAwait(false),
        };

        async ValueTask<TValue> EnsureNativeValueAsync()
        {
            PortableValue? existing = await this.Source.ReadStateAsync<PortableValue>(key, scopeName, cancellationToken).ConfigureAwait(false);
            bool legacyEntry = existing is null &&
                await Kit.IWorkflowContextExtensions.HasLegacyTopicEntryAsync(this.Source, key, scopeName!, forWrite: true, cancellationToken).ConfigureAwait(false);
            bool initialized = false;
            TValue result = await this.Source.ReadOrInitStateAsync(key, () =>
            {
                initialized = true;
                return initialStateFactory();
            }, legacyEntry ? VariableScopeNames.Topic : scopeName, cancellationToken).ConfigureAwait(false);
            if (legacyEntry)
            {
                PortableValue legacyValue = await ReadLegacyValueAsync().ConfigureAwait(false);
                await this.Source.QueueStateUpdateAsync(key, legacyValue.ToPortableObject(), scopeName, cancellationToken).ConfigureAwait(false);
            }
            if (initialized || legacyEntry)
            {
                await CompleteInitializationAsync(legacyEntry).ConfigureAwait(false);
            }
            return result;
        }

        async ValueTask<TValue> EnsureFormulaValueAsync()
        {
            Debug.Assert(typeof(TValue) == typeof(FormulaValue), "It is a bug to call this method with TValue not === FormulaValue");
            FormulaValue? result = this.State.Get(key, scopeName);

            if (result is null or BlankValue)
            {
                bool legacyEntry = await Kit.IWorkflowContextExtensions.HasLegacyTopicEntryAsync(this.Source, key, scopeName!, forWrite: true, cancellationToken).ConfigureAwait(false);
                PortableValue? legacyValue = legacyEntry ? await ReadLegacyValueAsync().ConfigureAwait(false) : null;
                result = legacyValue is null ? initialStateFactory() as FormulaValue : legacyValue.ToFormula();
                if (result is null)
                {
                    throw new InvalidOperationException($"The initial state factory for key '{key}' in scope '{scopeName}' did not return a FormulaValue.");
                }

                this.State.Set(key, result, scopeName);
                await this.Source.QueueStateUpdateAsync(key, legacyValue is null ? result.AsPortable() : legacyValue.ToPortableObject(), scopeName, cancellationToken)
                                 .ConfigureAwait(false);
                await CompleteInitializationAsync(legacyEntry).ConfigureAwait(false);
            }

            return (TValue)(object)result!; // The null analyzer is confused here, but it is impossible to hit this line with result is null
        }

        async ValueTask<PortableValue> ReadLegacyValueAsync() =>
            await this.Source.ReadStateAsync<PortableValue>(key, VariableScopeNames.Topic, cancellationToken).ConfigureAwait(false)
                ?? throw new InvalidOperationException($"The existing state for key '{key}' in scope '{VariableScopeNames.Topic}' is missing.");

        async ValueTask CompleteInitializationAsync(bool legacyEntry)
        {
            SensitivityLevel sensitivity = legacyEntry
                ? await this.Source.ReadStateAsync<SensitivityLevel>(key, WorkflowFormulaState.GetSensitivityScopeName(scopeName!), cancellationToken).ConfigureAwait(false)
                : SensitivityLevel.None;
            await this.QueueSensitivityUpdateAsync(key, scopeName, sensitivity, cancellationToken).ConfigureAwait(false);
            this.State.SetSensitivity(key, scopeName, sensitivity);
            if (legacyEntry)
            {
                await this.Source.QueueStateUpdateAsync<object>(key, null, VariableScopeNames.Topic, cancellationToken).ConfigureAwait(false);
            }
        }
    }

    /// <inheritdoc/>
    public ValueTask<HashSet<string>> ReadStateKeysAsync(string? scopeName = null, CancellationToken cancellationToken = default)
    {
        scopeName = IsManagedScope(scopeName) ? WorkflowFormulaState.GetScopeName(scopeName) : scopeName;
        return this.Source.ReadStateKeysAsync(scopeName, cancellationToken);
    }

    /// <inheritdoc/>
    public ValueTask SendMessageAsync(object message, string? targetId = null, CancellationToken cancellationToken = default)
        => this.Source.SendMessageAsync(message, targetId, cancellationToken);

    public async ValueTask UpdateStateAsync<T>(
        string key,
        T? value,
        string? scopeName,
        bool allowSystem,
        SensitivityLevel sensitivity = SensitivityLevel.None,
        CancellationToken cancellationToken = default)
    {
        bool isManagedScope =
            scopeName is not null && // null scope cannot be managed
            VariableScopeNames.IsValidName(scopeName);

        if (!isManagedScope)
        {
            // Not a managed scope, just pass through.  This is valid when a declarative
            // workflow has been ejected to code (where DeclarativeWorkflowContext is also utilized).
            await this.Source.QueueStateUpdateAsync(key, value, scopeName, cancellationToken).ConfigureAwait(false);
            return;
        }

        if (!ManagedScopes.Contains(scopeName!) && !allowSystem)
        {
            throw new DeclarativeActionException($"Cannot manage variable definitions in scope: '{scopeName}'.");
        }

        scopeName = WorkflowFormulaState.GetScopeName(scopeName);

        bool legacyEntry = await Kit.IWorkflowContextExtensions.HasLegacyTopicEntryAsync(this.Source, key, scopeName, forWrite: true, cancellationToken).ConfigureAwait(false);
        switch (value)
        {
            case null:
            case UnassignedValue:
            case BlankValue:
                await QueueEmptyStateAsync().ConfigureAwait(false);
                break;
            case FormulaValue formulaValue:
                await QueueFormulaStateAsync(formulaValue).ConfigureAwait(false);
                break;
            case DataValue dataValue:
                await QueueDataValueStateAsync(dataValue).ConfigureAwait(false);
                break;
            default:
                await QueueNativeStateAsync(value).ConfigureAwait(false);
                break;
        }
        if (legacyEntry)
        {
            await this.Source.QueueStateUpdateAsync<object>(key, null, VariableScopeNames.Topic, cancellationToken).ConfigureAwait(false);
        }

        async ValueTask QueueEmptyStateAsync()
        {
            if (isManagedScope)
            {
                this.State.Set(key, FormulaValue.NewBlank(), scopeName, sensitivity);
            }
            await this.Source.QueueStateUpdateAsync(key, UnassignedValue.Instance, scopeName, cancellationToken).ConfigureAwait(false);
            await this.QueueSensitivityUpdateAsync(key, scopeName, sensitivity, cancellationToken).ConfigureAwait(false);
        }

        async ValueTask QueueFormulaStateAsync(FormulaValue formulaValue)
        {
            if (isManagedScope)
            {
                this.State.Set(key, formulaValue, scopeName, sensitivity);
            }

            await this.Source.QueueStateUpdateAsync(key, formulaValue.AsPortable(), scopeName, cancellationToken).ConfigureAwait(false);
            await this.QueueSensitivityUpdateAsync(key, scopeName, sensitivity, cancellationToken).ConfigureAwait(false);
        }

        async ValueTask QueueDataValueStateAsync(DataValue dataValue)
        {
            FormulaValue formulaValue = dataValue.ToFormula();

            if (isManagedScope)
            {
                this.State.Set(key, formulaValue, scopeName, sensitivity);
            }

            await this.Source.QueueStateUpdateAsync(key, formulaValue.AsPortable(), scopeName, cancellationToken).ConfigureAwait(false);
            await this.QueueSensitivityUpdateAsync(key, scopeName, sensitivity, cancellationToken).ConfigureAwait(false);
        }

        async ValueTask QueueNativeStateAsync(object rawValue)
        {
            FormulaValue formulaValue = rawValue.ToFormula();

            if (isManagedScope)
            {
                this.State.Set(key, formulaValue, scopeName, sensitivity);
            }

            await this.Source.QueueStateUpdateAsync(key, formulaValue.AsPortable(), scopeName, cancellationToken).ConfigureAwait(false);
            await this.QueueSensitivityUpdateAsync(key, scopeName, sensitivity, cancellationToken).ConfigureAwait(false);
        }
    }

    private ValueTask QueueSensitivityUpdateAsync(string key, string? scopeName, SensitivityLevel sensitivity, CancellationToken cancellationToken)
    {
        if (scopeName is null || (!ManagedScopes.Contains(scopeName) && scopeName != VariableScopeNames.Environment))
        {
            return default;
        }

        return WorkflowFormulaState.QueueSensitivityUpdateAsync(this.Source, key, scopeName, sensitivity, delete: false, cancellationToken);
    }
}
