// Copyright (c) Microsoft. All rights reserved.

using System.Net;
using System.Security.Cryptography;
using System.Text;
using Microsoft.Extensions.Options;
using Microsoft.Net.Http.Headers;

namespace Microsoft.Agents.AI.DevUI;

/// <summary>
/// Endpoint filter that enforces the DevUI security posture: loopback-only
/// access by default, plus optional bearer-token authentication.
/// </summary>
internal sealed class DevUIAuthFilter : IEndpointFilter
{
    private const string BearerScheme = "Bearer";

    private readonly DevUIOptions _options;
    private readonly byte[]? _expectedTokenBytes;
    private readonly ILogger<DevUIAuthFilter> _logger;

    /// <summary>
    /// Gets a value indicating whether a bearer token is required by this filter
    /// (either via <see cref="DevUIOptions.AuthToken"/> or the
    /// <c>DEVUI_AUTH_TOKEN</c> environment variable).
    /// </summary>
    public bool TokenRequired => this._expectedTokenBytes is { Length: > 0 };

    public DevUIAuthFilter(IOptions<DevUIOptions> options, ILogger<DevUIAuthFilter> logger)
    {
        ArgumentNullException.ThrowIfNull(options);
        ArgumentNullException.ThrowIfNull(logger);
        this._options = options.Value;
        this._logger = logger;

        var configuredToken = !string.IsNullOrEmpty(this._options.AuthToken)
            ? this._options.AuthToken
            : Environment.GetEnvironmentVariable(DevUIOptions.AuthTokenEnvironmentVariable);

        this._expectedTokenBytes = !string.IsNullOrEmpty(configuredToken)
            ? Encoding.UTF8.GetBytes(configuredToken)
            : null;
    }

    public async ValueTask<object?> InvokeAsync(EndpointFilterInvocationContext context, EndpointFilterDelegate next)
    {
        var httpContext = context.HttpContext;
        var remoteIp = httpContext.Connection.RemoteIpAddress;
        var isLoopback = remoteIp is not null && IPAddress.IsLoopback(remoteIp);

        if (!isLoopback && !this._options.AllowRemoteAccess)
        {
            this._logger.LogWarning(
                "Rejected non-loopback DevUI request from {RemoteIp}. Set DevUIOptions.AllowRemoteAccess to permit remote callers.",
                remoteIp);
            return Results.Problem(
                statusCode: StatusCodes.Status403Forbidden,
                title: "DevUI access denied",
                detail: "DevUI is restricted to loopback callers by default. Enable AllowRemoteAccess to permit remote access.");
        }

        if (this._expectedTokenBytes is { Length: > 0 } expected && !TokenIsValid(httpContext.Request, expected))
        {
            httpContext.Response.Headers[HeaderNames.WWWAuthenticate] = BearerScheme;
            return Results.Problem(
                statusCode: StatusCodes.Status401Unauthorized,
                title: "DevUI authentication required",
                detail: "Provide a valid bearer token via the Authorization header.");
        }

        return await next(context).ConfigureAwait(false);
    }

    private static bool TokenIsValid(HttpRequest request, byte[] expected)
    {
        if (!request.Headers.TryGetValue(HeaderNames.Authorization, out var headerValues))
        {
            return false;
        }

        foreach (var header in headerValues)
        {
            if (string.IsNullOrEmpty(header))
            {
                continue;
            }

            const int PrefixLength = 7; // "Bearer "
            if (header.Length <= PrefixLength ||
                !header.StartsWith(BearerScheme, StringComparison.OrdinalIgnoreCase) ||
                header[BearerScheme.Length] != ' ')
            {
                continue;
            }

            var presented = Encoding.UTF8.GetBytes(header.AsSpan(PrefixLength).Trim().ToString());
            if (CryptographicOperations.FixedTimeEquals(presented, expected))
            {
                return true;
            }
        }

        return false;
    }
}
