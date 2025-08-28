// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Collections.Immutable;
using System.Linq;
using Microsoft.Agents.Workflows.Declarative.Extensions;
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

    public WorkflowScopes()
    {
        this._scopes = VariableScopeNames.AllScopes.ToDictionary(scopeName => scopeName, scopeName => new WorkflowScope(scopeName)).ToImmutableDictionary();
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

    /// <summary>
    /// The set of variables for a specific action scope.
    /// </summary>
    private sealed class WorkflowScope(string scopeName) : Dictionary<string, FormulaValue>
    {
        public string Name => scopeName;

        public void Reset()
        {
            foreach (string variableName in this.Keys.ToArray())
            {
                this.Reset(variableName);
            }
        }

        public void Reset(string variableName)
        {
            if (this.TryGetValue(variableName, out FormulaValue? value))
            {
                this[variableName] = value.Type.NewBlank();
            }
        }

        public RecordValue BuildRecord()
        {
            return FormulaValue.NewRecordFromFields(GetFields());

            IEnumerable<NamedValue> GetFields()
            {
                foreach (KeyValuePair<string, FormulaValue> kvp in this)
                {
                    yield return new NamedValue(kvp.Key, kvp.Value);
                }
            }
        }

        public RecordDataValue BuildState()
        {
            RecordDataValue.Builder recordBuilder = new();

            foreach (KeyValuePair<string, FormulaValue> kvp in this)
            {
                recordBuilder.Properties.Add(kvp.Key, kvp.Value.ToDataValue());
            }

            return recordBuilder.Build();
        }
    }
}
