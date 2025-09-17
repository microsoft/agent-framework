// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Frozen;
using System.Collections.Generic;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.Workflows.Declarative.Extensions;
using Microsoft.Bot.ObjectModel;
using Microsoft.PowerFx;
using Microsoft.PowerFx.Types;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.Workflows.Declarative.PowerFx;

/// <summary>
/// Contains all variables scopes for a workflow.
/// </summary>
internal sealed class WorkflowFormulaState
{
    // ISSUE #488 - Update default scope for workflows to `Workflow` (instead of `Topic`)
    public const string DefaultScopeName = VariableScopeNames.Topic;

    private static readonly FrozenSet<string> s_mutableScopes =
        [
            VariableScopeNames.Topic,
            VariableScopeNames.Global,
            VariableScopeNames.System,
        ];

    private readonly Dictionary<string, WorkflowScope> _scopes;
    private int _isInitialized;

    public RecalcEngine Engine { get; }

    public WorkflowExpressionEngine Evaluator { get; }

    public WorkflowFormulaState(RecalcEngine engine)
    {
        this.Engine = engine;
        this.Evaluator = new WorkflowExpressionEngine(engine);
        this._scopes = VariableScopeNames.AllScopes.ToDictionary(scopeName => scopeName, scopeName => new WorkflowScope(scopeName));
        this.Bind();
    }

    public FormulaValue Get(PropertyPath variablePath) => this.Get(Throw.IfNull(variablePath.VariableName), variablePath.VariableScopeName);

    public FormulaValue Get(string variableName, string? scopeName = null)
    {
        if (this.GetScope(scopeName).TryGetValue(variableName, out FormulaValue? value))
        {
            return value;
        }

        return FormulaValue.NewBlank();
    }

    public void ResetAll(string? scopeName = null)
    {
        if (scopeName is not null)
        {
            this.GetScope(scopeName).ResetAll();
        }
        else
        {
            foreach (string targetScope in VariableScopeNames.AllScopes)
            {
                this.GetScope(targetScope).ResetAll();
            }
        }

        this.Bind();
    }

    public void Reset(PropertyPath variablePath) => this.Reset(Throw.IfNull(variablePath.VariableName), variablePath.VariableScopeName);

    public void Reset(string variableName, string? scopeName = null)
    {
        this.GetScope(scopeName).Reset(variableName);
        this.Bind();
    }

    public void Set(PropertyPath variablePath, FormulaValue value) => this.Set(Throw.IfNull(variablePath.VariableName), value, variablePath.VariableScopeName);

    public void Set(string variableName, FormulaValue value, string? scopeName = null)
    {
        this.GetScope(scopeName)[variableName] = value;
        this.Bind();
    }

    public bool SetInitialized() => Interlocked.CompareExchange(ref this._isInitialized, 1, 0) == 0;

    public async ValueTask RestoreAsync(IWorkflowContext context, CancellationToken cancellationToken)
    {
        if (!this.SetInitialized())
        {
            return;
        }

        await Task.WhenAll(s_mutableScopes.Select(scopeName => ReadScopeAsync(scopeName))).ConfigureAwait(false);

        async Task ReadScopeAsync(string scopeName)
        {
            HashSet<string> keys = await context.ReadStateKeysAsync(scopeName).ConfigureAwait(false);
            foreach (string key in keys)
            {
                object? value = await context.ReadStateAsync<object>(key, scopeName).ConfigureAwait(false);
                if (value is null || value is UnassignedValue)
                {
                    value = FormulaValue.NewBlank();
                }
                this.Set(key, value.ToFormula(), scopeName);
            }

            this.Bind(scopeName);
        }
    }

    public RecordValue BuildRecord(string scopeName) => this.GetScope(scopeName).BuildRecord();

    public void Bind(string? targetScope = null)
    {
        if (targetScope is not null)
        {
            Bind(targetScope);
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
            this.Engine.DeleteFormula(scopeName);
            this.Engine.UpdateVariable(scopeName, scopeRecord);
        }
    }

    private WorkflowScope GetScope(string? scopeName)
    {
        scopeName ??= WorkflowFormulaState.DefaultScopeName;

        if (!VariableScopeNames.IsValidName(scopeName))
        {
            throw new DeclarativeActionException($"Invalid variable scope name: '{scopeName}'.");
        }

        return this._scopes[scopeName];
    }

    /// <summary>
    /// The set of variables for a specific action scope.
    /// </summary>
    private sealed class WorkflowScope(string scopeName) : Dictionary<string, FormulaValue>
    {
        public string Name => scopeName;

        public void ResetAll()
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
    }
}
