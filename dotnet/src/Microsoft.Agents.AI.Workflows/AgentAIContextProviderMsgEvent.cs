// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Workflows;

internal sealed class AgentAIContextProviderMsgEvent(IReadOnlyList<ChatMessage> messages) : WorkflowEvent(messages)
{
    public IReadOnlyList<ChatMessage> Messages { get; } = messages;
}
