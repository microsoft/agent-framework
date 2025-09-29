// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Bot.ObjectModel;

namespace Microsoft.Agents.AI.Workflows.Declarative.CodeGen;

internal partial class CopyConversationMessagesTemplate
{
    public CopyConversationMessagesTemplate(CopyConversationMessages model)
    {
        this.Model = this.Initialize(model);
        this.UseAgentProvider = true;
    }

    public CopyConversationMessages Model { get; }
}
