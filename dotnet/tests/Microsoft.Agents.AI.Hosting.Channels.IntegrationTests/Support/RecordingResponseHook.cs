// Copyright (c) Microsoft. All rights reserved.

using System.Threading;
using System.Threading.Tasks;

namespace Microsoft.Agents.AI.Hosting.Channels.IntegrationTests.Support;

/// <summary>Response hook that records whether it was invoked and returns the result unchanged.</summary>
internal sealed class RecordingResponseHook : IChannelResponseHook
{
    public bool Invoked { get; private set; }

    public ValueTask<HostedRunResult> OnResponseAsync(HostedRunResult result, ChannelResponseContext context, CancellationToken cancellationToken)
    {
        this.Invoked = true;
        return new ValueTask<HostedRunResult>(result);
    }
}
