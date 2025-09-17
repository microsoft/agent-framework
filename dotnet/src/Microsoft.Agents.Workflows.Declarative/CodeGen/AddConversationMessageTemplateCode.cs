// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.Workflows.Declarative.Extensions;
using Microsoft.Bot.ObjectModel;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.Workflows.Declarative.CodeGen;

internal partial class AddConversationMessageTemplate
{
    public AddConversationMessageTemplate(AddConversationMessage model)
    {
        this.Model = model;
        this.Id = model.GetId();
        this.Name = this.Id.FormatType();
        this.Message = Throw.IfNull(this.Model.Message?.Path);
    }

    public AddConversationMessage Model { get; }

    public string Id { get; }
    public string Name { get; }
    public PropertyPath Message { get; }
}
