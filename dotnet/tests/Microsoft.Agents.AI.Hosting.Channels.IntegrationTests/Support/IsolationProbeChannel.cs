// Copyright (c) Microsoft. All rights reserved.

using Microsoft.AspNetCore.Builder;
using Microsoft.AspNetCore.Http;
using Microsoft.AspNetCore.Routing;

namespace Microsoft.Agents.AI.Hosting.Channels.IntegrationTests.Support;

/// <summary>
/// Minimal channel whose single GET <c>/probe</c> route captures <see cref="IsolationKeys.Current"/> INSIDE
/// the request and echoes it, so tests can exercise the full filter -&gt; AsyncLocal -&gt; handler hop end to end.
/// Mounted at the app root (<see cref="Path"/> = <see cref="string.Empty"/>).
/// </summary>
internal sealed class IsolationProbeChannel : Channel
{
    public override string Name => "isolation-probe";

    public override string Path => string.Empty;

    public override ChannelContribution Contribute(ChannelContext context) => new()
    {
        Routes =
        [
            endpoints => endpoints.MapGet("/probe", () =>
            {
                var keys = IsolationKeys.Current;
                return Results.Text(keys is null
                    ? "absent"
                    : $"user={keys.UserKey ?? string.Empty};chat={keys.ChatKey ?? string.Empty}");
            }),
        ],
    };
}
