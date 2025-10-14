// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Frozen;
using System.Collections.Generic;
using System.Diagnostics;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Workflows.Declarative.Extensions;
using Microsoft.Bot.ObjectModel;
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

    private readonly Dictionary<string, WorkflowScope> _scopes;

    private int _isInitialized;

    public RecalcEngine Engine { get; }

    public WorkflowExpressionEngine Evaluator { get; }

    public WorkflowFormulaState(RecalcEngine engine)
    {
        this._scopes = VariableScopeNames.AllScopes.ToDictionary(scopeName => GetScopeName(scopeName), _ => new WorkflowScope());

        this.Engine = engine;
        this.Evaluator = new WorkflowExpressionEngine(engine);
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

    public void Set(string variableName, FormulaValue value, string? scopeName = null) =>
        this.GetScope(scopeName ?? DefaultScopeName)[variableName] = value;

    public bool SetInitialized() => Interlocked.CompareExchange(ref this._isInitialized, 1, 0) == 0;

    public async ValueTask RestoreAsync(IWorkflowContext context, CancellationToken cancellationToken)
    {
        if (!this.SetInitialized())
        {
            return;
        }

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
                if (value is null)
                {
                    this.Set(key, FormulaValue.NewBlank(), scopeName);
                    continue;
                }
                FormulaValue formulaValue = value.ToFormula();
                this.Set(key, formulaValue, scopeName);
                Debug.WriteLine($"RESTORED: {scopeName}.{key} => {formulaValue.Type}");
            }

            this.Bind(scopeName);
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
    private sealed class WorkflowScope : Dictionary<string, FormulaValue>;
}
