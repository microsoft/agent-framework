// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Hosting.Channels.IntegrationTests.Support;

/// <summary>
/// Run hook that materializes the Responses channel's parsed input (an <see cref="IReadOnlyList{ChatMessage}"/>)
/// into the concrete <c>List&lt;ChatMessage&gt;</c> that a sequential agent workflow expects as its input.
/// </summary>
internal sealed class ChatMessageListRunHook : IChannelRunHook
{
    public ValueTask<ChannelRequest> OnRequestAsync(ChannelRequest request, ChannelRunHookContext context, CancellationToken cancellationToken)
    {
        if (request.Input is IEnumerable<ChatMessage> messages)
        {
            return new(new ChannelRequest(request) { Input = messages.ToList() });
        }

        return new(request);
    }
}
