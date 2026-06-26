// Copyright (c) Microsoft. All rights reserved.

using System.Threading;
using System.Threading.Tasks;

namespace Microsoft.Agents.AI.Hosting.Channels.IntegrationTests.Support;

/// <summary>
/// Run hook that records the <see cref="ChannelRequest"/> it sees and returns it unchanged. Because supplying
/// a run hook replaces the channel's default option-stripping behavior, parsed options survive to the agent,
/// and the captured request exposes the parsed <see cref="ChannelIdentity"/> / options for assertions.
/// </summary>
internal sealed class CapturingRunHook : IChannelRunHook
{
    public ChannelRequest? Last { get; private set; }

    public ValueTask<ChannelRequest> OnRequestAsync(ChannelRequest request, ChannelRunHookContext context, CancellationToken cancellationToken)
    {
        this.Last = request;
        return new ValueTask<ChannelRequest>(request);
    }
}
