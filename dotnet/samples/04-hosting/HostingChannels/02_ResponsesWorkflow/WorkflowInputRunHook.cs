// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Hosting.Channels;
using Microsoft.Extensions.AI;

namespace ResponsesWorkflowSample;

/// <summary>
/// Run hook that adapts the Responses channel's parsed input (a <see cref="ChatMessage"/> list) into the
/// workflow's typed string input before the host invokes the <see cref="Microsoft.Agents.AI.Workflows.Workflow"/>.
/// </summary>
internal sealed class WorkflowInputRunHook : IChannelRunHook
{
    public ValueTask<ChannelRequest> OnRequestAsync(ChannelRequest request, ChannelRunHookContext context, CancellationToken cancellationToken)
    {
        var text = request.Input switch
        {
            string s => s,
            IEnumerable<ChatMessage> messages => string.Join("\n", messages.Select(m => m.Text)),
            _ => request.Input.ToString() ?? string.Empty,
        };

        return new(new ChannelRequest(request) { Input = text });
    }
}