// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.Workflows.Declarative.Extensions;
using Microsoft.Bot.ObjectModel;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.Workflows.Declarative.CodeGen;

internal partial class CreateConversationTemplate
{
    public CreateConversationTemplate(CreateConversation model)
    {
        this.Model = model;
        this.Id = model.GetId();
        this.Name = this.Id.FormatType();
        this.ConversationId = Throw.IfNull(this.Model.ConversationId?.Path);
    }

    public CreateConversation Model { get; }

    public string Id { get; }
    public string Name { get; }
    public PropertyPath ConversationId { get; }
}
