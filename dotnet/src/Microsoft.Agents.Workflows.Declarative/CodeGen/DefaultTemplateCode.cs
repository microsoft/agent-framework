// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Bot.ObjectModel;

namespace Microsoft.Agents.Workflows.Declarative.CodeGen;

internal partial class DefaultTemplate
{
    public DefaultTemplate(DialogAction model, string executorComment)
    {
        this.Initialize(model);
        this.Comment = executorComment;
    }

    public string Comment { get; }
}
