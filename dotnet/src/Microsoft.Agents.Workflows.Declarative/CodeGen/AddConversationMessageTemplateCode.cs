// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Frozen;
using System.Collections.Generic;
using Microsoft.Agents.Workflows.Declarative.Extensions;
using Microsoft.Bot.ObjectModel;
using Microsoft.Extensions.AI;
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

    public const string DefaultRole = nameof(ChatRole.User);

    public static readonly FrozenDictionary<AgentMessageRoleWrapper, string> RoleMap =
        new Dictionary<AgentMessageRoleWrapper, string>()
        {
            [AgentMessageRoleWrapper.Get(AgentMessageRole.User)] = nameof(ChatRole.User),
            [AgentMessageRoleWrapper.Get(AgentMessageRole.Agent)] = nameof(ChatRole.Assistant),
        }.ToFrozenDictionary();
}
