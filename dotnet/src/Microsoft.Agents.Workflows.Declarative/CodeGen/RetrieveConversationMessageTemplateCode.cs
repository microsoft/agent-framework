// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Bot.ObjectModel;

namespace Microsoft.Agents.Workflows.Declarative.CodeGen;

internal partial class RetrieveConversationMessageTemplate
{
    public RetrieveConversationMessageTemplate(RetrieveConversationMessage model)
    {
        this.Model = this.Initialize(model);
    }

    public RetrieveConversationMessage Model { get; }
}
