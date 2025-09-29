// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Bot.ObjectModel;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI.Workflows.Declarative.CodeGen;

internal partial class CreateConversationTemplate
{
    public CreateConversationTemplate(CreateConversation model)
    {
        this.Model = this.Initialize(model);
        this.ConversationId = Throw.IfNull(this.Model.ConversationId);
        this.UseAgentProvider = true;
    }

    public CreateConversation Model { get; }

    public PropertyPath ConversationId { get; }
}
