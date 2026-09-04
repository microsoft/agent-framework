// Copyright (c) Microsoft. All rights reserved.

using System;
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

    private readonly Dictionary<string, WorkflowScope> _scopes;

    private HashSet<(string ScopeName, string VariableName)>? _trackedChanges;

    private int _isInitialized;

    public RecalcEngine Engine { get; }

    public WorkflowExpressionEngine Evaluator { get; }

    /// <summary>
    /// Gets the branch-local workflow-conversation staging buffer, when this state is running
    /// inside a parallel Foreach iteration.
    /// </summary>
    internal WorkflowConversationMessageBuffer? ConversationMessageBuffer { get; set; }

    /// <summary>
    /// Receives action failures while this state is executing as an isolated parallel
    /// Foreach branch. The runner uses this side channel so a peer cancellation cannot
    /// hide an error that was already raised by the branch action.
    /// </summary>
    internal Action<Exception>? ParallelFailureReporter { get; set; }

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

    public void Set(string variableName, FormulaValue value, string? scopeName = null)
    {
        string normalizedScopeName = GetScopeName(scopeName);
        this.GetScope(normalizedScopeName)[variableName] = value;
        this._trackedChanges?.Add((normalizedScopeName, variableName));
    }

    /// <summary>
    /// Captures a portable deep snapshot of every workflow variable scope.
    /// </summary>
    public WorkflowStateSnapshot CaptureSnapshot()
    {
        WorkflowStateEntry[] entries =
        [
            .. VariableScopeNames.AllScopes
                .Select(GetScopeName)
                .Distinct()
                .SelectMany(
                    scopeName =>
                        this.Keys(scopeName)
                            .OrderBy(variableName => variableName, StringComparer.Ordinal)
                            .Select(
                                variableName =>
                                    new WorkflowStateEntry(
                                        scopeName,
                                        variableName,
                                        new PortableValue(this.Get(variableName, scopeName).AsPortable())))),
        ];

        return new(entries);
    }

    /// <summary>
    /// Creates an isolated state instance from a previously captured snapshot.
    /// </summary>
    public static WorkflowFormulaState CreateBranch(RecalcEngine engine, WorkflowStateSnapshot snapshot)
    {
        WorkflowFormulaState branch = new(engine);
        foreach (WorkflowStateEntry entry in snapshot.Entries)
        {
            branch.Set(entry.VariableName, entry.Value.ToFormula(), entry.ScopeName);
        }

        return branch;
    }

    /// <summary>
    /// Starts recording the variables written after branch initialization.
    /// </summary>
    public void BeginTrackingChanges() => this._trackedChanges = [];

    /// <summary>
    /// Captures the current values of all variables written since change tracking began.
    /// </summary>
    public WorkflowStateChange[] CaptureChanges() =>
        this._trackedChanges is null
            ? []
            :
            [
                .. this._trackedChanges
                    .OrderBy(change => change.ScopeName, System.StringComparer.Ordinal)
                    .ThenBy(change => change.VariableName, System.StringComparer.Ordinal)
                    .Select(
                        change =>
                            new WorkflowStateChange(
                                change.ScopeName,
                                change.VariableName,
                                new PortableValue(this.Get(change.VariableName, change.ScopeName).AsPortable()))),
            ];

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

internal sealed record WorkflowStateEntry(string ScopeName, string VariableName, PortableValue Value);

internal sealed record WorkflowStateChange(string ScopeName, string VariableName, PortableValue Value);

internal sealed record WorkflowStateSnapshot(IReadOnlyList<WorkflowStateEntry> Entries);
