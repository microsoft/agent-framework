// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Frozen;
using System.Collections.Generic;
using System.Diagnostics;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Workflows.Declarative.Extensions;
using Microsoft.Agents.ObjectModel;
using Microsoft.PowerFx;
using Microsoft.PowerFx.Types;

namespace Microsoft.Agents.AI.Workflows.Declarative.PowerFx;

/// <summary>
/// Contains all variables scopes for a workflow.
/// </summary>
internal sealed class WorkflowFormulaState
{
    public const string DefaultScopeName = VariableScopeNames.Local;

    public static readonly FrozenSet<string> RestorableScopes =
        [
            VariableScopeNames.Local,
            VariableScopeNames.Global,
            VariableScopeNames.System,
        ];

    private const string SensitivityScopePrefix = "__Microsoft_Agents_AI_Workflows_Declarative_Sensitivity:";

    private readonly Dictionary<string, WorkflowScope> _scopes;

    private Dictionary<string, WorkflowScope> _initialScopes;

    private int _isInitialized;

    public RecalcEngine Engine { get; }

    public WorkflowExpressionEngine Evaluator { get; }

    public WorkflowFormulaState(RecalcEngine engine)
    {
        this._scopes = VariableScopeNames.AllScopes.ToDictionary(scopeName => GetScopeName(scopeName), _ => new WorkflowScope());
        this._initialScopes = this.CreateScopeSnapshot();

        this.Engine = engine;
        this.Evaluator = new WorkflowExpressionEngine(this);
        this.Bind();
    }

    public IEnumerable<string> Keys(string scopeName) => this.GetScope(scopeName).Keys;

    public FormulaValue Get(string variableName, string? scopeName = null)
    {
        if (this.GetScope(scopeName).TryGetValue(variableName, out FormulaValue? value))
        {
            return value;
        }

        return FormulaValue.NewBlank();
    }

    public void Set(string variableName, FormulaValue value, string? scopeName = null, SensitivityLevel sensitivity = SensitivityLevel.None)
    {
        WorkflowScope scope = this.GetScope(scopeName ?? DefaultScopeName);
        scope[variableName] = value;
        scope.Sensitivities[variableName] = sensitivity;
    }

    public SensitivityLevel GetSensitivity(string variableName, string? scopeName = null)
    {
        if (scopeName is not null && !VariableScopeNames.IsValidName(scopeName))
        {
            return SensitivityLevel.None;
        }

        WorkflowScope scope = this.GetScope(scopeName ?? DefaultScopeName);
        return scope.Sensitivities.TryGetValue(variableName, out SensitivityLevel sensitivity) ? sensitivity : SensitivityLevel.None;
    }

    public void SetSensitivity(string variableName, string? scopeName, SensitivityLevel sensitivity) =>
        this.GetScope(scopeName ?? DefaultScopeName).Sensitivities[variableName] = sensitivity;

    public bool SetInitialized() => Interlocked.CompareExchange(ref this._isInitialized, 1, 0) == 0;

    public void CaptureInitialState()
    {
        this._initialScopes = this.CreateScopeSnapshot();
    }

    public void Reset()
    {
        this.RestoreInitialState();
        Interlocked.Exchange(ref this._isInitialized, 0);
        this.Bind();
    }

    public async ValueTask RestoreAsync(IWorkflowContext context, CancellationToken cancellationToken)
    {
        if (!this.SetInitialized())
        {
            return;
        }

        this.RestoreInitialState();

        Stopwatch timer = Stopwatch.StartNew();
        Debug.WriteLine("RESTORE CHECKPOINT - BEGIN");
        await Task.WhenAll(RestorableScopes.Select(scopeName => ReadScopeAsync(scopeName))).ConfigureAwait(false);
        Debug.WriteLine($"RESTORE CHECKPOINT - COMPLETE [{timer.Elapsed}]");

        async Task ReadScopeAsync(string scopeName)
        {
            HashSet<string> keys = await context.ReadStateKeysAsync(scopeName, cancellationToken).ConfigureAwait(false);
            foreach (string key in keys)
            {
                PortableValue? value = await context.ReadStateAsync<PortableValue>(key, scopeName, cancellationToken).ConfigureAwait(false);
                SensitivityLevel sensitivity = await context.ReadStateAsync<SensitivityLevel>(key, GetSensitivityScopeName(scopeName), cancellationToken).ConfigureAwait(false);
                if (value is null)
                {
                    this.Set(key, FormulaValue.NewBlank(), scopeName, sensitivity);
                    continue;
                }
                FormulaValue formulaValue = value.ToFormula();
                this.Set(key, formulaValue, scopeName, sensitivity);
                Debug.WriteLine($"RESTORED: {scopeName}.{key} => {formulaValue.Type}");
            }

            this.Bind(scopeName);
        }
    }

    private Dictionary<string, WorkflowScope> CreateScopeSnapshot() =>
        this._scopes.ToDictionary(scope => scope.Key, scope => new WorkflowScope(scope.Value));

    private void RestoreInitialState()
    {
        foreach (KeyValuePair<string, WorkflowScope> initialScopeEntry in this._initialScopes)
        {
            WorkflowScope scope = this._scopes[initialScopeEntry.Key];
            scope.Clear();
            scope.Sensitivities.Clear();
            foreach (KeyValuePair<string, FormulaValue> initialValueEntry in initialScopeEntry.Value)
            {
                scope[initialValueEntry.Key] = initialValueEntry.Value;
            }

            foreach (KeyValuePair<string, SensitivityLevel> initialSensitivityEntry in initialScopeEntry.Value.Sensitivities)
            {
                scope.Sensitivities[initialSensitivityEntry.Key] = initialSensitivityEntry.Value;
            }
        }
    }

    public void Bind(string? scopeNameToBind = null)
    {
        if (scopeNameToBind is not null)
        {
            Bind(scopeNameToBind);
            if (VariableScopeNames.GetNamespaceFromName(scopeNameToBind) == VariableNamespace.Component)
            {
                Bind(scopeNameToBind, VariableScopeNames.Topic);
            }
        }
        else
        {
            foreach (string scopeName in VariableScopeNames.AllScopes)
            {
                Bind(scopeName);
            }

            Bind(DefaultScopeName, VariableScopeNames.Topic);
        }

        void Bind(string scopeName, string? targetScope = null)
        {
            targetScope = GetScopeName(targetScope ?? scopeName);
            RecordValue scopeRecord = this.GetScope(scopeName).ToRecord();
            this.Engine.DeleteFormula(targetScope);
            this.Engine.UpdateVariable(targetScope, scopeRecord);
        }
    }

    private WorkflowScope GetScope(string? scopeName) => this._scopes[GetScopeName(scopeName)];

    public static string GetSensitivityScopeName(string scopeName) => $"{SensitivityScopePrefix}{GetScopeName(scopeName)}";

    public static string GetScopeName(string? scopeName)
    {
        WorkflowDiagnostics.SetFoundryProduct();

        scopeName ??= DefaultScopeName;

        return
            VariableScopeNames.GetNamespaceFromName(scopeName) switch
            {
                // Always alias component level scope as "Local"
                VariableNamespace.Component => DefaultScopeName,
                VariableNamespace.Unknown => throw new DeclarativeActionException($"Invalid variable scope name: '{scopeName}'."),
                _ => scopeName,
            };
    }

    /// <summary>
    /// The set of variables for a specific action scope.
    /// </summary>
    private sealed class WorkflowScope : Dictionary<string, FormulaValue>
    {
        public WorkflowScope()
        {
        }

        public WorkflowScope(IDictionary<string, FormulaValue> values)
            : base(values)
        {
            if (values is WorkflowScope scope)
            {
                foreach (KeyValuePair<string, SensitivityLevel> sensitivity in scope.Sensitivities)
                {
                    this.Sensitivities[sensitivity.Key] = sensitivity.Value;
                }
            }
        }

        public Dictionary<string, SensitivityLevel> Sensitivities { get; } = [];
    }
}
