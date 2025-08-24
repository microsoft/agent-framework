// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading.Tasks;
using Microsoft.Bot.ObjectModel;
using Microsoft.Bot.ObjectModel.Abstractions;
using Microsoft.Bot.ObjectModel.Analysis;
using Microsoft.Bot.ObjectModel.PowerFx;
using Microsoft.Bot.ObjectModel.Telemetry;
using Microsoft.PowerFx.Types;

namespace Microsoft.Agents.Workflows.Declarative.PowerFx;

internal static class WorkflowDiagnostics
{
    public static void InitializeModel(this WorkflowScopes scopes, AdaptiveDialog workflowElement)
    {
        WorkflowOperationLogger operationLogger = new();
        WorkflowFeatureConfiguration featureConfig = new();
        SemanticModel semanticModel = workflowElement.GetSemanticModel(new PowerFxExpressionChecker(featureConfig), featureConfig, operationLogger);
        foreach (VariableInformationDiagnostic variableDiagnostic in semanticModel.GetVariables(workflowElement.SchemaName).Where(x => !x.IsSystemVariable).Select(v => v.ToDiagnostic()))
        {
            if (variableDiagnostic?.Path?.VariableName is null)
            {
                continue;
            }

            scopes.Set(variableDiagnostic.Path.VariableName, variableDiagnostic.Path.VariableScopeName ?? VariableScopeNames.Topic, FormulaValue.NewBlank(variableDiagnostic.Type.ToFormulaType()));
        }
    }

    private sealed class WorkflowOperationLogger : IOperationLogger
    {
        public T Execute<T>(string activity, Func<T> function) => function.Invoke();

        public T Execute<T>(string activity, Func<T> function, IEnumerable<KeyValuePair<string, string>> dimensions) => function.Invoke();

        public Task<T> ExecuteAsync<T>(string activity, Func<Task<T>> function) => function.Invoke();

        public Task<T> ExecuteAsync<T>(string activity, Func<Task<T>> function, IEnumerable<KeyValuePair<string, string>> dimensions) => function.Invoke();
    }

    private sealed class WorkflowFeatureConfiguration : IFeatureConfiguration
    {
        public long GetInt64Value(string settingName, long defaultValue) => defaultValue;

        public string GetStringValue(string settingName, string defaultValue) => defaultValue;

        public bool IsEnvironmentFeatureEnabled(string featureName, bool defaultValue) => true;

        public bool IsTenantFeatureEnabled(string featureName, bool defaultValue) => true;
    }
}
