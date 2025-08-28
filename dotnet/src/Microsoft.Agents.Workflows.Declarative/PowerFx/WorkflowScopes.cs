// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Collections.Immutable;
using System.Linq;
using Microsoft.Bot.ObjectModel;
using Microsoft.PowerFx;
using Microsoft.PowerFx.Types;

namespace Microsoft.Agents.Workflows.Declarative.PowerFx;

/// <summary>
/// Contains all action scopes for a process.
/// </summary>
internal sealed class WorkflowScopes
{
    // ISSUE #488 - Update default scope for workflows to `Workflow` (instead of `Topic`)
    public const string DefaultScopeName = VariableScopeNames.Topic;

    private readonly ImmutableDictionary<string, WorkflowScope> _scopes;

    public WorkflowScopes(Dictionary<string, WorkflowScope>? scopes = null)
    {
        this._scopes = VariableScopeNames.AllScopes.ToDictionary(scopeName => scopeName, scopeName => GetScope(scopeName)).ToImmutableDictionary();

        WorkflowScope GetScope(string scopeName)
        {
            if (scopes is not null && scopes.TryGetValue(scopeName, out WorkflowScope? scope))
            {
                return scope;
            }

            return new WorkflowScope(scopeName);
        }
    }

    public FormulaValue Get(string variableName, string? scopeName = null)
    {
        if (this._scopes[scopeName ?? WorkflowScopes.DefaultScopeName].TryGetValue(variableName, out FormulaValue? value))
        {
            return value;
        }

        return FormulaValue.NewBlank();
    }

    public void Clear(string scopeName) => this._scopes[scopeName].Reset();

    public void Reset(string variableName, string? scopeName = null) => this._scopes[scopeName ?? WorkflowScopes.DefaultScopeName].Reset(variableName);

    public void Set(string variableName, FormulaValue value, string? scopeName = null) => this._scopes[scopeName ?? WorkflowScopes.DefaultScopeName][variableName] = value;

    public RecordValue BuildRecord(string scopeName) => this._scopes[scopeName].BuildRecord();

    public RecordDataValue BuildState()
    {
        return DataValue.RecordFromFields(BuildStateFields());

        IEnumerable<KeyValuePair<string, DataValue>> BuildStateFields()
        {
            foreach (KeyValuePair<string, WorkflowScope> kvp in this._scopes)
            {
                yield return new(kvp.Key, kvp.Value.BuildState());
            }
        }
    }

    public void Bind(RecalcEngine engine, string? type = null)
    {
        if (type is not null)
        {
            Bind(type);
        }
        else
        {
            foreach (string scopeName in VariableScopeNames.AllScopes)
            {
                Bind(scopeName);
            }
        }

        void Bind(string scopeName)
        {
            RecordValue scopeRecord = this.BuildRecord(scopeName);
            engine.DeleteFormula(scopeName);
            engine.UpdateVariable(scopeName, scopeRecord);
        }
    }
}
