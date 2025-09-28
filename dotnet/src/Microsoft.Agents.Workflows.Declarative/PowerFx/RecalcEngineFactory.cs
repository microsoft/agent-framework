﻿// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.Workflows.Declarative.PowerFx.Functions;
using Microsoft.Bot.ObjectModel;
using Microsoft.PowerFx;
using Microsoft.PowerFx.Types;

namespace Microsoft.Agents.Workflows.Declarative.PowerFx;

internal static class RecalcEngineFactory
{
    public static RecalcEngine Create(
        int? maximumExpressionLength = null,
        int? maximumCallDepth = null)
    {
        RecalcEngine engine = new(CreateConfig());

        foreach (string scopeName in VariableScopeNames.AllScopes)
        {
            engine.UpdateVariable(WorkflowFormulaState.GetScopeName(scopeName), RecordValue.Empty());
        }
        engine.UpdateVariable(VariableScopeNames.Topic, RecordValue.Empty());

        return engine;

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
            config.AddFunction(new UserMessage());

            return config;
        }
    }
}
