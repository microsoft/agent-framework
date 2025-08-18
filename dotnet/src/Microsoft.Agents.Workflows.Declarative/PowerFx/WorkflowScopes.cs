// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Collections.Immutable;
using Microsoft.Bot.ObjectModel;
using Microsoft.PowerFx;
using Microsoft.PowerFx.Types;

namespace Microsoft.Agents.Workflows.Declarative.PowerFx;

/// <summary>
/// Contains all action scopes for a process.
/// </summary>
internal sealed class WorkflowScopes
{
    private readonly ImmutableDictionary<WorkflowScopeType, WorkflowScope> _scopes;

    public WorkflowScopes()
    {
        Dictionary<WorkflowScopeType, WorkflowScope> scopes =
            new()
            {
                { WorkflowScopeType.Env, [] },
                { WorkflowScopeType.Topic, [] },
                { WorkflowScopeType.Global, [] },
                { WorkflowScopeType.System, [] },
            };

        this._scopes = scopes.ToImmutableDictionary();
    }

    public RecordValue BuildRecord(WorkflowScopeType scope) => this._scopes[scope].BuildRecord();

    public RecordDataValue BuildState()
    {
        return DataValue.RecordFromFields(BuildStateFields());

        IEnumerable<KeyValuePair<string, DataValue>> BuildStateFields()
        {
            foreach (KeyValuePair<WorkflowScopeType, WorkflowScope> kvp in this._scopes)
            {
                yield return new(kvp.Key.Name, kvp.Value.BuildState());
            }
        }
    }

    public void Bind(RecalcEngine engine, WorkflowScopeType? type = null)
    {
        if (type is not null)
        {
            Bind(type);
        }
        else
        {
            Bind(WorkflowScopeType.Topic);
            Bind(WorkflowScopeType.Global);
            Bind(WorkflowScopeType.Env);
            Bind(WorkflowScopeType.System);
        }

        void Bind(WorkflowScopeType scope)
        {
            RecordValue scopeRecord = this.BuildRecord(scope);
            engine.DeleteFormula(scope.Name);
            engine.UpdateVariable(scope.Name, scopeRecord);
        }
    }

    public FormulaValue Get(string name, WorkflowScopeType? type = null)
    {
        if (this._scopes[type ?? WorkflowScopeType.Topic].TryGetValue(name, out FormulaValue? value))
        {
            return value;
        }

        return FormulaValue.NewBlank();
    }

    public void Clear(WorkflowScopeType type) => this._scopes[type].Clear();

    public void Remove(string name) => this.Remove(name, WorkflowScopeType.Topic);

    public void Remove(string name, WorkflowScopeType type) => this._scopes[type].Remove(name);

    public void Set(string name, FormulaValue value) => this.Set(name, WorkflowScopeType.Topic, value);

    public void Set(string name, WorkflowScopeType type, FormulaValue value) => this._scopes[type][name] = value;
}
