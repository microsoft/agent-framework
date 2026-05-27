// Copyright (c) Microsoft. All rights reserved.

namespace Microsoft.Agents.AI.DevUI;

/// <summary>
/// Options that control the security posture of the DevUI HTTP surface.
/// </summary>
/// <remarks>
/// DevUI exposes agent metadata that is sensitive in production contexts:
/// system instructions, tool definitions, model identifiers, and workflow
/// structure. By default, DevUI rejects any request whose remote endpoint
/// is not a loopback address. Hosts that intentionally expose DevUI on a
/// non-loopback interface must opt in via <see cref="AllowRemoteAccess"/>
/// and should also configure <see cref="AuthToken"/> or
/// <see cref="ConfigureEndpoints"/> to attach an authorization policy.
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
    /// When <see langword="false"/>, any request whose
    /// <see cref="ConnectionInfo.RemoteIpAddress"/> is
    /// not a loopback address (or is missing) is rejected with HTTP 403 before
    /// reaching the DevUI handlers. Enable only when the host is responsible
    /// for fronting DevUI with its own authentication, network policy, or both.
    /// </remarks>
    public bool AllowRemoteAccess { get; set; }

    /// <summary>
    /// Gets or sets a shared bearer token required on every DevUI request.
    /// When <see langword="null"/> or empty, the value of the
    /// <c>DEVUI_AUTH_TOKEN</c> environment variable is used instead.
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
    public Action<IEndpointConventionBuilder>? ConfigureEndpoints { get; set; }
}
