// Copyright (c) Microsoft. All rights reserved.

using System.Collections;
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
internal sealed class WorkflowScopes : IEnumerable<WorkflowScope>
{
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

    IEnumerator IEnumerable.GetEnumerator() => this.GetEnumerator();

    public IEnumerator<WorkflowScope> GetEnumerator() => this._scopes.Values.GetEnumerator();

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
            Bind(VariableScopeNames.Topic);
            Bind(VariableScopeNames.Global);
            Bind(VariableScopeNames.Environment);
            Bind(VariableScopeNames.System);
        }

        void Bind(string scopeName)
        {
            RecordValue scopeRecord = this.BuildRecord(scopeName);
            engine.DeleteFormula(scopeName);
            engine.UpdateVariable(scopeName, scopeRecord);
        }
    }

    public FormulaValue Get(string name, string? scopeName = null)
    {
        if (this._scopes[scopeName ?? VariableScopeNames.Topic].TryGetValue(name, out FormulaValue? value))
        {
            return value;
        }

        return FormulaValue.NewBlank();
    }

    public void Clear(string scopeName) => this._scopes[scopeName].Clear();

    public void Remove(string name) => this.Remove(name, VariableScopeNames.Topic);

    public void Remove(string name, string scopeName) => this._scopes[scopeName].Remove(name);

    public void Set(string name, FormulaValue value) => this.Set(name, VariableScopeNames.Topic, value);

    public void Set(string name, string scopeName, FormulaValue value) => this._scopes[scopeName][name] = value;
}
