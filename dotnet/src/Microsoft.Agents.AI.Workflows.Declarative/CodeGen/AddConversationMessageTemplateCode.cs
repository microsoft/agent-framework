// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Frozen;
using System.Collections.Generic;
using Microsoft.Bot.ObjectModel;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Workflows.Declarative.CodeGen;

internal partial class AddConversationMessageTemplate
{
    public AddConversationMessageTemplate(AddConversationMessage model)
    {
        this.Model = this.Initialize(model);
        this.Message = this.Model.Message?.Path;
        this.UseAgentProvider = true;
    }

    public AddConversationMessage Model { get; }

    public PropertyPath? Message { get; }

    public const string DefaultRole = nameof(ChatRole.User);

    public static readonly FrozenDictionary<AgentMessageRoleWrapper, string> RoleMap =
        new Dictionary<AgentMessageRoleWrapper, string>()
        {
            [AgentMessageRoleWrapper.Get(AgentMessageRole.User)] = nameof(ChatRole.User),
            [AgentMessageRoleWrapper.Get(AgentMessageRole.Agent)] = nameof(ChatRole.Assistant),
        }.ToFrozenDictionary();
}
