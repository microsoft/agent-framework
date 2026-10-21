// Copyright (c) Microsoft. All rights reserved.

namespace Microsoft.Agents.AI.DevUI;

/// <summary>
/// Options that control the security posture of the DevUI HTTP surface.
/// </summary>
/// <remarks>
/// DevUI is intended for trusted development environments and is not
/// recommended as a production hosting surface.
/// <para>
/// DevUI exposes agent metadata that is sensitive in production contexts:
/// system instructions, tool definitions, model identifiers, and workflow
/// structure. By default, DevUI requires a loopback peer and loopback Host,
/// and rejects cross-site state-changing browser requests. Hosts that
/// intentionally expose DevUI directly on a non-loopback interface must opt in
/// via <see cref="AllowRemoteAccess"/>. The built-in local checks are not a
/// production or public reverse-proxy authentication boundary. Reverse-proxied
/// exposure requires host-owned authentication and network policy, normally
/// together with <see cref="AllowRemoteAccess"/> set to <see langword="true"/>.
/// </para>
/// </remarks>
public sealed class DevUIOptions
{
    /// <summary>
    /// Environment variable inspected for a default bearer token when
    /// <see cref="AuthToken"/> is not explicitly set.
    /// </summary>
    public const string AuthTokenEnvironmentVariable = "DEVUI_AUTH_TOKEN";

    /// <summary>
    /// Gets or sets a value indicating whether DevUI may be served to
    /// non-loopback callers. Defaults to <see langword="false"/>.
    /// </summary>
    /// <remarks>
    /// When <see langword="false"/>, requests require a loopback
    /// <see cref="ConnectionInfo.RemoteIpAddress"/> and a localhost or loopback
    /// IP Host header. State-changing requests with a mismatched or invalid
    /// Origin, or with <c>Sec-Fetch-Site: cross-site</c>, are also rejected.
    /// These checks apply to the DevUI endpoints and the standard
    /// <c>/v1/responses</c> and <c>/v1/conversations</c> paths. Enable only
    /// when the host is responsible for its own network and browser-request
    /// protections. In particular, these checks do not authenticate the
    /// original caller when a reverse proxy makes the connection appear local.
    /// Public or production reverse-proxy exposure requires host-owned
    /// authentication and network policy, normally with this option set to
    /// <see langword="true"/>.
    /// </remarks>
    public bool AllowRemoteAccess { get; set; }

    /// <summary>
    /// Gets or sets a shared bearer token required on the UI and entity
    /// endpoints mapped by <c>MapDevUI()</c>. The token is not automatically
    /// imposed on separately mapped standard <c>/v1/responses</c> or
    /// <c>/v1/conversations</c> routes. When <see langword="null"/> or empty,
    /// the value of the <c>DEVUI_AUTH_TOKEN</c> environment variable is used
    /// instead.
    /// </summary>
    /// <remarks>
    /// When a token is configured, requests must include the header
    /// <c>Authorization: Bearer &lt;token&gt;</c>. Comparison is performed
    /// in constant time. This is a convenience for development scenarios.
    /// Production hosts should prefer a real ASP.NET Core authentication
    /// scheme attached via <see cref="ConfigureEndpoints"/>.
    /// </remarks>
    public string? AuthToken { get; set; }

    /// <summary>
    /// Gets or sets a callback invoked with the DevUI endpoint group so the
    /// host can attach authorization, rate limiting, or other endpoint
    /// conventions (for example
    /// <c>group.RequireAuthorization("DevUIPolicy")</c>).
    /// </summary>
    /// <remarks>
    /// This callback does not apply to separately mapped OpenAI endpoints.
    /// Hosts that need custom authorization on those endpoints must attach it
    /// when mapping them.
    /// </remarks>
    public Action<IEndpointConventionBuilder>? ConfigureEndpoints { get; set; }
}
