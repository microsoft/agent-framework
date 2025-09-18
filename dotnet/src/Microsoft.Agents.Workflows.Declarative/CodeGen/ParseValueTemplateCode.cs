// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Bot.ObjectModel;

namespace Microsoft.Agents.Workflows.Declarative.CodeGen;

internal partial class ParseValueTemplate
{
    public ParseValueTemplate(ParseValue model)
    {
        this.Model = this.Initialize(model);
    }

    public ParseValue Model { get; }
}
