// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Linq;
using Microsoft.Agents.Workflows.Declarative.Extensions;
using Microsoft.Bot.ObjectModel;
using Microsoft.Bot.ObjectModel.Abstractions;
using Microsoft.Bot.ObjectModel.Analysis;
using Microsoft.Bot.ObjectModel.PowerFx;
using Microsoft.PowerFx.Types;

namespace Microsoft.Agents.Workflows.Declarative.PowerFx;

internal static class WorkflowDiagnostics
{
    private static readonly WorkflowFeatureConfiguration s_semanticFeatureConfig = new();

    public static void InitializeDefaults(this WorkflowScopes scopes, AdaptiveDialog workflowElement)
    {
        scopes.InitializeSemanticModel(workflowElement);
    }

    private static void InitializeSemanticModel(this WorkflowScopes scopes, AdaptiveDialog workflowElement)
    {
        SemanticModel semanticModel = workflowElement.GetSemanticModel(new PowerFxExpressionChecker(s_semanticFeatureConfig), s_semanticFeatureConfig);
        foreach (VariableInformationDiagnostic variableDiagnostic in semanticModel.GetVariables(workflowElement.SchemaName).Where(x => !x.IsSystemVariable).Select(v => v.ToDiagnostic()))
        {
            Console.WriteLine($":: {variableDiagnostic?.Path?.VariableName ?? "?"}");
            if (variableDiagnostic?.Path?.VariableName is null)
            {
                continue;
            }

            FormulaValue defaultValue = ReadValue(variableDiagnostic) ?? ReadBlank(variableDiagnostic);

            if (variableDiagnostic.Path.VariableScopeName?.Equals(VariableScopeNames.System, StringComparison.OrdinalIgnoreCase) ?? false)
            {
                // %%% TODO: Verify supported variables
            }

            scopes.Set(variableDiagnostic.Path.VariableName, variableDiagnostic.Path.VariableScopeName ?? VariableScopeNames.Topic, defaultValue);
        }

        static FormulaValue? ReadValue(VariableInformationDiagnostic diagnostic) => diagnostic.ConstantValue?.ToFormulaValue();

        //static FormulaValue? ReadValue(string variableName)
        //{
        //    string? variableValue = Environment.GetEnvironmentVariable(variableName); // %%% TODO: Is provided as `ConstantValue` ???
        //    return string.IsNullOrEmpty(variableValue) ? null : FormulaValue.New(variableValue);
        //}

        static FormulaValue ReadBlank(VariableInformationDiagnostic diagnostic) => diagnostic.Type.NewBlank();
    }

    private sealed class WorkflowFeatureConfiguration : IFeatureConfiguration
    {
        public long GetInt64Value(string settingName, long defaultValue) => defaultValue;

        public string GetStringValue(string settingName, string defaultValue) => defaultValue;

        public bool IsEnvironmentFeatureEnabled(string featureName, bool defaultValue) => true;

        public bool IsTenantFeatureEnabled(string featureName, bool defaultValue) => true;
    }
}
