// Copyright (c) Microsoft. All rights reserved.

using Microsoft.PowerFx;
using Microsoft.PowerFx.Types;

namespace Microsoft.Agents.Workflows.Declarative.PowerFx;

internal static class RecalcEngineFactory
{
    public static RecalcEngine Create(
        WorkflowScopes scopes,
        int? maximumExpressionLength = null,
        int? maximumCallDepth = null)
    {
        RecalcEngine engine = new(CreateConfig());

        SetScope(WorkflowScopeType.Topic);
        SetScope(WorkflowScopeType.Global);
        SetScope(WorkflowScopeType.Env);
        SetScope(WorkflowScopeType.System);

        return engine;

        void SetScope(WorkflowScopeType scope)
        {
            RecordValue record = scopes.BuildRecord(scope);
            engine.UpdateVariable(scope.Name, record);
        }

        PowerFxConfig CreateConfig()
        {
            PowerFxConfig config = new(Features.PowerFxV1);

            if (maximumExpressionLength is not null)
            {
                config.MaximumExpressionLength = maximumExpressionLength.Value;
            }

            if (maximumCallDepth is not null)
            {
                config.MaxCallDepth = maximumCallDepth.Value;
            }

            config.EnableSetFunction();

            return config;
        }
    }
}
