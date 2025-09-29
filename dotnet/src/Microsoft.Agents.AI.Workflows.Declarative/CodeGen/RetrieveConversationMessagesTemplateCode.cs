// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Frozen;
using System.Collections.Generic;
using Microsoft.Bot.ObjectModel;

namespace Microsoft.Agents.AI.Workflows.Declarative.CodeGen;

internal partial class RetrieveConversationMessagesTemplate
{
    public RetrieveConversationMessagesTemplate(RetrieveConversationMessages model)
    {
        this.Model = this.Initialize(model);
        this.UseAgentProvider = true;
    }

    public RetrieveConversationMessages Model { get; }

    public const string DefaultSort = "false";

    public static readonly FrozenDictionary<AgentMessageSortOrderWrapper, string> SortMap =
        new Dictionary<AgentMessageSortOrderWrapper, string>()
        {
            [AgentMessageSortOrderWrapper.Get(AgentMessageSortOrder.NewestFirst)] = "true",
            [AgentMessageSortOrderWrapper.Get(AgentMessageSortOrder.OldestFirst)] = "false",
        }.ToFrozenDictionary();
}
