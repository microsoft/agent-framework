// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using Microsoft.Agents.AI.Workflows.Declarative.Extensions;
using Microsoft.Agents.ObjectModel;
using Microsoft.Agents.ObjectModel.Abstractions;
using Microsoft.Agents.ObjectModel.Analysis;
using Microsoft.Agents.ObjectModel.PowerFx;
using Microsoft.Extensions.Configuration;
using Microsoft.PowerFx.Types;

namespace Microsoft.Agents.AI.Workflows.Declarative.PowerFx;

internal sealed record class WorkflowTypeInfo(ISet<string> EnvironmentVariables, IList<VariableInformationDiagnostic> UserVariables);

internal static class WorkflowDiagnostics
{
    private static readonly WorkflowFeatureConfiguration s_semanticFeatureConfig = new();

    public static void SetFoundryProduct()
    {
        if (!ProductContext.IsLocalScopeSupported())
        {
            ProductContext.SetContext(Product.Foundry);
        }
    }

    public static WorkflowTypeInfo Describe<TElement>(this TElement workflowElement) where TElement : BotElement, IDialogBase
    {
        SemanticModel semanticModel = workflowElement.GetSemanticModel(new PowerFxExpressionChecker(s_semanticFeatureConfig), s_semanticFeatureConfig);

        return
            new WorkflowTypeInfo(
                semanticModel.GetAllEnvironmentVariablesReferencedInTheBot(),
                [.. semanticModel.GetVariables(workflowElement.SchemaName.Value).Where(x => !x.IsSystemVariable).Select(v => v.ToDiagnostic())]);
    }

    public static void Initialize<TElement>(this WorkflowFormulaState scopes, TElement workflowElement, IConfiguration? configuration) where TElement : BotElement, IDialogBase
    {
        scopes.InitializeSystem();

        SemanticModel semanticModel = workflowElement.GetSemanticModel(new PowerFxExpressionChecker(s_semanticFeatureConfig), s_semanticFeatureConfig);
        scopes.InitializeEnvironment(semanticModel, configuration);
        scopes.InitializeDefaults(semanticModel, workflowElement.SchemaName.Value);
    }

    private static void InitializeEnvironment(this WorkflowFormulaState scopes, SemanticModel semanticModel, IConfiguration? configuration)
    {
        foreach (string variableName in semanticModel.GetAllEnvironmentVariablesReferencedInTheBot())
        {
            string? environmentValue = configuration is not null ? configuration[variableName] : Environment.GetEnvironmentVariable(variableName);
            FormulaValue variableValue = string.IsNullOrEmpty(environmentValue) ? FormulaType.String.NewBlank() : FormulaValue.New(environmentValue);
            scopes.Set(variableName, variableValue, VariableScopeNames.Environment);
        }
    }

    private static void InitializeDefaults(this WorkflowFormulaState scopes, SemanticModel semanticModel, string schemaName)
    {
        foreach (VariableInformationDiagnostic variableDiagnostic in semanticModel.GetVariables(schemaName).Where(x => !x.IsSystemVariable).Select(v => v.ToDiagnostic()))
        {
            // Use the same PropertyPath fallback/remap as runtime reads/writes so dotted
            // refs like "Local.Triage" (which ObjectModel 2026.2.4.1 returns with null
            // VariableName/NamespaceAlias) and the "Local" scope alias are not silently
            // dropped from the initial state.
            // TODO(https://github.com/microsoft/agent-framework/issues/5905): drop the
            // workaround once the ObjectModel regression is fixed.
            PropertyPath? path = variableDiagnostic?.Path;
            if (path is null)
            {
                continue;
            }

            string? variableName = path.GetVariableName();
            if (variableName is null)
            {
                continue;
            }

            string? scopeName = path.GetNamespaceAlias();

            FormulaValue defaultValue = variableDiagnostic!.ConstantValue?.ToFormula() ?? variableDiagnostic.Type.NewBlank();

            if (scopeName?.Equals(VariableScopeNames.System, StringComparison.OrdinalIgnoreCase) is true &&
                !SystemScope.AllNames.Contains(variableName))
            {
                throw new DeclarativeModelException($"Variable '{variableName}' is not a supported system variable.");
            }

            scopes.Set(variableName, defaultValue, scopeName ?? WorkflowFormulaState.DefaultScopeName);
        }
    }

    private sealed class WorkflowFeatureConfiguration : IFeatureConfiguration
    {
        public long GetInt64Value(string settingName, long defaultValue) => defaultValue;

        public string GetStringValue(string settingName, string defaultValue) => defaultValue;

        public bool IsEnvironmentFeatureEnabled(string featureName, bool defaultValue) => true;

        public bool IsTenantFeatureEnabled(string featureName, bool defaultValue) => true;
    }
}
