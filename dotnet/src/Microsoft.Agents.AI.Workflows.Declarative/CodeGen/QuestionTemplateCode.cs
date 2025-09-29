// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Bot.ObjectModel;

namespace Microsoft.Agents.AI.Workflows.Declarative.CodeGen;

internal partial class QuestionTemplate
{
    public QuestionTemplate(Question model)
    {
        this.Model = this.Initialize(model);
    }

    public Question Model { get; }
}
