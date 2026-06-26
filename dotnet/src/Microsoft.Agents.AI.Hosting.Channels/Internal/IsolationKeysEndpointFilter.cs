// Copyright (c) Microsoft. All rights reserved.

using System.Threading.Tasks;
using Microsoft.AspNetCore.Http;

namespace Microsoft.Agents.AI.Hosting.Channels;

/// <summary>
/// Endpoint filter that lifts the Foundry <c>x-agent-user-isolation-key</c> / <c>x-agent-chat-isolation-key</c>
/// request headers into <see cref="IsolationKeys.Current"/> for the duration of the request and resets it
/// afterwards.
/// </summary>
/// <remarks>
/// The host applies this filter to every channel route only when the Foundry hosting environment flag is
/// present. When neither header is supplied the request passes through untouched, so local-development and
/// non-Foundry requests behave as if the filter were absent.
/// </remarks>
internal sealed class IsolationKeysEndpointFilter : IEndpointFilter
{
    public async ValueTask<object?> InvokeAsync(EndpointFilterInvocationContext context, EndpointFilterDelegate next)
    {
        var headers = context.HttpContext.Request.Headers;
        var userKey = headers[IsolationKeys.UserHeader].ToString();
        var chatKey = headers[IsolationKeys.ChatHeader].ToString();

        if (string.IsNullOrEmpty(userKey) && string.IsNullOrEmpty(chatKey))
        {
            return await next(context).ConfigureAwait(false);
        }

        var previous = IsolationKeys.Current;
        IsolationKeys.Current = new IsolationKeys(
            string.IsNullOrEmpty(userKey) ? null : userKey,
            string.IsNullOrEmpty(chatKey) ? null : chatKey);
        try
        {
            return await next(context).ConfigureAwait(false);
        }
        finally
        {
            IsolationKeys.Current = previous;
        }
    }
}
