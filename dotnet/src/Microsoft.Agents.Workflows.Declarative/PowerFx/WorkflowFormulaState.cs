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

namespace Microsoft.Agents.Workflows.Declarative.PowerFx;

/// <summary>
/// Contains all variables scopes for a workflow.
/// </summary>
internal sealed class WorkflowFormulaState
{
    // ISSUE #488 - Update default scope for workflows to `Workflow` (instead of `Topic`)
    public const string DefaultScopeName = VariableScopeNames.Topic;

    public static readonly FrozenSet<string> RestorableScopes =
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
        this._scopes = VariableScopeNames.AllScopes.ToDictionary(scopeName => scopeName, scopeName => new WorkflowScope());
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

        await Task.WhenAll(RestorableScopes.Select(scopeName => ReadScopeAsync(scopeName))).ConfigureAwait(false);

        async Task ReadScopeAsync(string scopeName)
        {
            HashSet<string> keys = await context.ReadStateKeysAsync(scopeName).ConfigureAwait(false);
            foreach (string key in keys)
            {
                object? value = await context.ReadStateAsync<object>(key, scopeName).ConfigureAwait(false);
                if (value is null or UnassignedValue)
                {
                    value = FormulaValue.NewBlank();
                }

                this.Set(key, value.ToFormula(), scopeName);
            }

            this.Bind(scopeName);
        }
    }

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
            RecordValue scopeRecord = this.GetScope(scopeName).ToRecord();
            this.Engine.DeleteFormula(scopeName);
            this.Engine.UpdateVariable(scopeName, scopeRecord);
        }
    }

    private WorkflowScope GetScope(string? scopeName)
    {
        scopeName ??= DefaultScopeName;

        if (!VariableScopeNames.IsValidName(scopeName))
        {
            throw new DeclarativeActionException($"Invalid variable scope name: '{scopeName}'.");
        }

        return this._scopes[scopeName];
    }

    /// <summary>
    /// The set of variables for a specific action scope.
    /// </summary>
    private sealed class WorkflowScope : Dictionary<string, FormulaValue>;
}
