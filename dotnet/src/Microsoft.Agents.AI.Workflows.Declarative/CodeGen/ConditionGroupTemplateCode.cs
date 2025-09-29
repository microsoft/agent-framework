// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Bot.ObjectModel;

namespace Microsoft.Agents.AI.Workflows.Declarative.CodeGen;

internal partial class ConditionGroupTemplate
{
    public ConditionGroupTemplate(ConditionGroup model)
    {
        this.Model = this.Initialize(model);
    }

    public ConditionGroup Model { get; }
}
