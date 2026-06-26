// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Runtime.CompilerServices;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.AspNetCore.Http;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Hosting.Channels.IntegrationTests.Support;

/// <summary>Run hook that rewrites the request input, to assert run-hook ordering (before the target).</summary>
internal sealed class RewriteInputRunHook(string replacement) : IChannelRunHook
{
    public ValueTask<ChannelRequest> OnRequestAsync(ChannelRequest request, ChannelRunHookContext context, CancellationToken cancellationToken) =>
        new(new ChannelRequest(request) { Input = replacement });
}

/// <summary>
/// Run hook that stamps <see cref="ChannelSession.IsolationKey"/> from a request header, simulating trusted
/// middleware. The channel never trusts wire input for the isolation key; this is how a host derives it.
/// </summary>
internal sealed class HeaderIsolationRunHook(IHttpContextAccessor accessor, string headerName) : IChannelRunHook
{
    public ValueTask<ChannelRequest> OnRequestAsync(ChannelRequest request, ChannelRunHookContext context, CancellationToken cancellationToken)
    {
        var key = accessor.HttpContext?.Request.Headers[headerName].ToString();
        if (string.IsNullOrEmpty(key))
        {
            return new(request);
        }

        var session = new ChannelSession(request.Session ?? new ChannelSession()) { IsolationKey = key };
        return new(new ChannelRequest(request) { Session = session });
    }
}

/// <summary>Response hook that uppercases the agent reply, to assert response-hook ordering (before serialize).</summary>
internal sealed class UppercaseResponseHook : IChannelResponseHook
{
    public ValueTask<HostedRunResult> OnResponseAsync(HostedRunResult result, ChannelResponseContext context, CancellationToken cancellationToken)
    {
        if (result is HostedRunResult<AgentResponse> typed)
        {
            var upper = typed.Result.Text.ToUpperInvariant();
            return new(typed.Replace(new AgentResponse(new ChatMessage(ChatRole.Assistant, upper))));
        }

        return new(result);
    }
}

/// <summary>Stream transform hook that prefixes a marker chunk, to assert the hook is applied while streaming.</summary>
internal sealed class PrefixStreamHook : IChannelStreamTransformHook
{
    public async IAsyncEnumerable<AgentResponseUpdate> TransformAsync(
        IAsyncEnumerable<AgentResponseUpdate> upstream,
        [EnumeratorCancellation] CancellationToken cancellationToken)
    {
        yield return new AgentResponseUpdate { Role = ChatRole.Assistant, Contents = [new TextContent("[X]")] };
        await foreach (var update in upstream.ConfigureAwait(false))
        {
            yield return update;
        }
    }
}
