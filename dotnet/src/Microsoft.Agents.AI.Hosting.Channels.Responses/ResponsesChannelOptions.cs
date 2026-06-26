// Copyright (c) Microsoft. All rights reserved.

using System;

namespace Microsoft.Agents.AI.Hosting.Channels.Responses;

/// <summary>
/// Configuration for <see cref="ResponsesChannel"/>.
/// </summary>
public sealed class ResponsesChannelOptions
{
    /// <summary>Mount root for the Responses route. Default <c>"/responses"</c>; use <c>""</c> for the app root.</summary>
    public string Path { get; set; } = "/responses";

    /// <summary>
    /// Optional run hook invoked after the channel parses the request and before the host invokes the target.
    /// Supplying a hook <b>replaces</b> the default behavior, which strips all parsed generation options so
    /// untrusted callers cannot inject parameters; a custom hook receives the request with options populated
    /// and decides what to forward.
    /// </summary>
    public IChannelRunHook? RunHook { get; set; }

    /// <summary>Optional response hook invoked before the channel serializes the originating response.</summary>
    public IChannelResponseHook? ResponseHook { get; set; }

    /// <summary>
    /// Optional stream-update hook applied by the host while the channel consumes streamed updates, before
    /// the channel renders Server-Sent-Events. Applies only to streaming requests.
    /// </summary>
    public IChannelStreamTransformHook? StreamTransformHook { get; set; }

    /// <summary>
    /// Optional factory that mints the per-request response id, receiving the caller's
    /// <c>previous_response_id</c> (or <see langword="null"/>) as a co-location hint. Default produces
    /// <c>resp_&lt;uuid&gt;</c>. Override when the host backing storage requires a different id format.
    /// </summary>
    public Func<string?, string>? ResponseIdFactory { get; set; }
}
