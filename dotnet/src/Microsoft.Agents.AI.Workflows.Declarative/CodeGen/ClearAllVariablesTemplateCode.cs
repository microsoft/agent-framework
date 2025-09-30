// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Frozen;
using System.Collections.Generic;
using Microsoft.Agents.AI.Workflows.Declarative.PowerFx;
using Microsoft.Bot.ObjectModel;

namespace Microsoft.Agents.AI.Workflows.Declarative.CodeGen;

internal partial class ClearAllVariablesTemplate
{
    public ClearAllVariablesTemplate(ClearAllVariables model)
    {
        this.Model = this.Initialize(model);
    }

    public ClearAllVariables Model { get; }

    public static readonly FrozenDictionary<VariablesToClearWrapper, string?> ScopeMap =
        new Dictionary<VariablesToClearWrapper, string?>()
        {
            [VariablesToClearWrapper.Get(VariablesToClear.AllGlobalVariables)] = VariableScopeNames.Global,
            [VariablesToClearWrapper.Get(VariablesToClear.ConversationScopedVariables)] = WorkflowFormulaState.DefaultScopeName,
        }.ToFrozenDictionary();
}
