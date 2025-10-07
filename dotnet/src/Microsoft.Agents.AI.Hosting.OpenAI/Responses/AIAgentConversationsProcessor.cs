// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.AspNetCore.Http;

namespace Microsoft.Agents.AI.Hosting.OpenAI.Responses;

internal sealed class AIAgentConversationsProcessor
{
#pragma warning disable IDE0052 // Remove unread private members
    private readonly AIAgent _aiAgent;
#pragma warning restore IDE0052 // Remove unread private members

    public AIAgentConversationsProcessor(AIAgent aiAgent)
    {
        this._aiAgent = aiAgent ?? throw new ArgumentNullException(nameof(aiAgent));
    }

    public async Task<IResult> GetConversationAsync(string conversationId, CancellationToken cancellationToken)
    {
        // TODO come back to it later
        throw new NotImplementedException();
    }
}
