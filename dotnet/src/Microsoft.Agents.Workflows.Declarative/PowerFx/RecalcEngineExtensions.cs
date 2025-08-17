// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Bot.ObjectModel;
using Microsoft.PowerFx;
using Microsoft.PowerFx.Types;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.Workflows.Declarative.PowerFx;

internal static class RecalcEngineExtensions
{
    public static void ClearScope(this RecalcEngine engine, WorkflowScopes scopes, WorkflowScopeType scope)
    {
        // Clear all scope values.
        scopes.Clear(scope);

        // Rebuild scope record and update engine
        engine.UpdateScope(scopes, scope);
    }

    public static void ClearScopedVariable(this RecalcEngine engine, WorkflowScopes scopes, PropertyPath variablePath) =>
        engine.ClearScopedVariable(scopes, WorkflowScopeType.Parse(variablePath.VariableScopeName), Throw.IfNull(variablePath.VariableName));

    public static void ClearScopedVariable(this RecalcEngine engine, WorkflowScopes scopes, WorkflowScopeType scope, string varName)
    {
        // Clear value.
        scopes.Remove(varName, scope);

        // Rebuild scope record and update engine
        engine.UpdateScope(scopes, scope);
    }

    public static void SetScopedVariable(this RecalcEngine engine, WorkflowScopes scopes, PropertyPath variablePath, FormulaValue value) =>
        engine.SetScopedVariable(scopes, WorkflowScopeType.Parse(variablePath.VariableScopeName), Throw.IfNull(variablePath.VariableName), value);

    public static void SetScopedVariable(this RecalcEngine engine, WorkflowScopes scopes, WorkflowScopeType scope, string varName, FormulaValue value)
    {
        // Assign value.
        scopes.Set(varName, scope, value);

        // Rebuild scope record and update engine
        engine.UpdateScope(scopes, scope);
    }

    public static void AssignScope(this RecalcEngine engine, string scopeName, RecordValue scopeRecord)
    {
        engine.DeleteFormula(scopeName);
        engine.UpdateVariable(scopeName, scopeRecord);
    }

    private static void UpdateScope(this RecalcEngine engine, WorkflowScopes scopes, WorkflowScopeType scope)
    {
        RecordValue scopeRecord = scopes.BuildRecord(scope);
        engine.AssignScope(scope.Name, scopeRecord);
    }
}
