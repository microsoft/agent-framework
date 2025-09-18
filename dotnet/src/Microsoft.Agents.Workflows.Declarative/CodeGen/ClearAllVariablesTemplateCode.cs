// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Frozen;
using System.Collections.Generic;
using Microsoft.Agents.Workflows.Declarative.Extensions;
using Microsoft.Bot.ObjectModel;

namespace Microsoft.Agents.Workflows.Declarative.CodeGen;

internal partial class ClearAllVariablesTemplate
{
    public ClearAllVariablesTemplate(ClearAllVariables model)
    {
        this.Model = model;
        this.Id = model.GetId();
        this.Name = this.Id.FormatType();
    }

    public ClearAllVariables Model { get; }

    public string Id { get; }
    public string Name { get; }

    public static readonly FrozenDictionary<VariablesToClearWrapper, string?> TopicMap =
        new Dictionary<VariablesToClearWrapper, string?>()
        {
            [VariablesToClearWrapper.Get(VariablesToClear.AllGlobalVariables)] = VariableScopeNames.Global,
            [VariablesToClearWrapper.Get(VariablesToClear.ConversationScopedVariables)] = VariableScopeNames.Topic,
        }.ToFrozenDictionary();
}
