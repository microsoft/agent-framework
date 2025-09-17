// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.Workflows.Declarative.Extensions;
using Microsoft.Bot.ObjectModel;

namespace Microsoft.Agents.Workflows.Declarative.CodeGen;

internal partial class RetrieveConversationMessagesTemplate
{
    public RetrieveConversationMessagesTemplate(RetrieveConversationMessages model)
    {
        this.Model = model;
        this.Id = model.GetId();
        this.Name = this.Id.FormatType();
    }

    public RetrieveConversationMessages Model { get; }

    public string Id { get; }
    public string Name { get; }
}
