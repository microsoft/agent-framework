// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Frozen;
using System.Collections.Generic;
using System.Linq;
using Microsoft.Agents.Workflows.Declarative.Extensions;
using Microsoft.Bot.ObjectModel;
using Microsoft.Bot.ObjectModel.Abstractions;
using Microsoft.Bot.ObjectModel.Analysis;
using Microsoft.Bot.ObjectModel.PowerFx;
using Microsoft.Extensions.Configuration;
using Microsoft.PowerFx.Types;

namespace Microsoft.Agents.Workflows.Declarative.PowerFx;

internal sealed record class WorkflowTypeInfo(FrozenSet<string> EnvironmentVariables, IEnumerable<VariableInformationDiagnostic> UserVariables);

internal static class WorkflowDiagnostics
{
    private static readonly WorkflowFeatureConfiguration s_semanticFeatureConfig = new();

    public static WorkflowTypeInfo Describe<TElement>(this TElement workflowElement) where TElement : BotElement, IDialogBase
    {
        SemanticModel semanticModel = workflowElement.GetSemanticModel(new PowerFxExpressionChecker(s_semanticFeatureConfig), s_semanticFeatureConfig);

        return
            new WorkflowTypeInfo(
                semanticModel.GetAllEnvironmentVariablesReferencedInTheBot().ToFrozenSet(),
                semanticModel.GetVariables(workflowElement.SchemaName.Value).Where(x => !x.IsSystemVariable).Select(v => v.ToDiagnostic()));
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
            if (variableDiagnostic?.Path?.VariableName is null)
            {
                continue;
            }

            FormulaValue defaultValue = variableDiagnostic.ConstantValue?.ToFormula() ?? variableDiagnostic.Type.NewBlank();

            if (variableDiagnostic.Path.VariableScopeName?.Equals(VariableScopeNames.System, StringComparison.OrdinalIgnoreCase) is true &&
                !SystemScope.AllNames.Contains(variableDiagnostic.Path.VariableName))
            {
                throw new DeclarativeModelException($"Variable '{variableDiagnostic.Path.VariableName}' is not a supported system variable.");
            }

            scopes.Set(variableDiagnostic.Path.VariableName, defaultValue, variableDiagnostic.Path.VariableScopeName ?? WorkflowFormulaState.DefaultScopeName);
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
