// Copyright (c) Microsoft. All rights reserved.

using System.Net;
using System.Security.Cryptography;
using System.Text;
using Microsoft.Extensions.Options;
using Microsoft.Net.Http.Headers;

namespace Microsoft.Agents.AI.DevUI;

/// <summary>
/// Validates the network origin, browser origin, and optional bearer token for DevUI requests.
/// </summary>
internal sealed class DevUIRequestValidator
{
    private const string BearerScheme = "Bearer";
    private const string SecFetchSiteHeader = "Sec-Fetch-Site";

    private readonly DevUIOptions _options;
    private readonly byte[]? _expectedTokenBytes;
    private readonly ILogger<DevUIRequestValidator> _logger;

    /// <summary>
    /// Initializes a new instance of the <see cref="DevUIRequestValidator"/> class.
    /// </summary>
    /// <param name="options">The configured DevUI access options.</param>
    /// <param name="logger">The logger used for rejected requests.</param>
    public DevUIRequestValidator(IOptions<DevUIOptions> options, ILogger<DevUIRequestValidator> logger)
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

    /// <summary>
    /// Gets a value indicating whether requests must include the configured bearer token.
    /// </summary>
    public bool TokenRequired => this._expectedTokenBytes is { Length: > 0 };

    /// <summary>
    /// Validates that a request satisfies the configured local access policy.
    /// </summary>
    /// <param name="context">The HTTP context to validate.</param>
    /// <returns>An error result when validation fails; otherwise, <see langword="null"/>.</returns>
    public IResult? ValidateLocalRequest(HttpContext context)
    {
        ArgumentNullException.ThrowIfNull(context);

        if (!this._options.AllowRemoteAccess)
        {
            var remoteIp = context.Connection.RemoteIpAddress;
            if (remoteIp is null || !IPAddress.IsLoopback(remoteIp))
            {
                DevUILog.RejectedNonLoopbackRequest(this._logger, remoteIp);
                return AccessDenied("DevUI is restricted to loopback callers by default. Enable AllowRemoteAccess to permit remote access.");
            }

            if (!HostIsLoopback(context.Request.Host))
            {
                return AccessDenied("DevUI requires a localhost or loopback IP Host header by default.");
            }

            if (IsStateChanging(context.Request.Method) && !BrowserRequestIsAllowed(context.Request))
            {
                return AccessDenied("DevUI rejected a cross-site browser request.");
            }
        }

        return null;
    }

    /// <summary>
    /// Validates that a request includes the optional configured DevUI bearer token.
    /// </summary>
    /// <param name="context">The HTTP context to validate.</param>
    /// <returns>An error result when validation fails; otherwise, <see langword="null"/>.</returns>
    public IResult? ValidateToken(HttpContext context)
    {
        ArgumentNullException.ThrowIfNull(context);

        if (this._expectedTokenBytes is { Length: > 0 } expected && !TokenIsValid(context.Request, expected))
        {
            context.Response.Headers[HeaderNames.WWWAuthenticate] = BearerScheme;
            return Results.Problem(
                statusCode: StatusCodes.Status401Unauthorized,
                title: "DevUI authentication required",
                detail: "Provide a valid bearer token via the Authorization header.");
        }

        return null;
    }

    private static IResult AccessDenied(string detail)
        => Results.Problem(
            statusCode: StatusCodes.Status403Forbidden,
            title: "DevUI access denied",
            detail: detail);

    private static bool BrowserRequestIsAllowed(HttpRequest request)
    {
        if (request.Headers.TryGetValue(SecFetchSiteHeader, out var fetchSiteValues))
        {
            foreach (var value in fetchSiteValues)
            {
                if (string.Equals(value?.Trim(), "cross-site", StringComparison.OrdinalIgnoreCase))
                {
                    return false;
                }
            }
        }

        if (!request.Headers.TryGetValue(HeaderNames.Origin, out var originValues))
        {
            return true;
        }

        if (originValues.Count != 1 ||
            !Uri.TryCreate(originValues[0], UriKind.Absolute, out var origin) ||
            !string.IsNullOrEmpty(origin.UserInfo) ||
            !string.Equals(origin.AbsolutePath, "/", StringComparison.Ordinal) ||
            !string.IsNullOrEmpty(origin.Query) ||
            !string.IsNullOrEmpty(origin.Fragment))
        {
            return false;
        }

        var requestPort = request.Host.Port ?? DefaultPort(request.Scheme);
        return string.Equals(origin.Scheme, request.Scheme, StringComparison.OrdinalIgnoreCase) &&
            HostsMatch(origin.Host, request.Host.Host) &&
            origin.Port == requestPort;
    }

    private static int DefaultPort(string scheme)
        => string.Equals(scheme, Uri.UriSchemeHttps, StringComparison.OrdinalIgnoreCase) ? 443 : 80;

    private static bool HostIsLoopback(HostString host)
    {
        var hostName = RemoveIpv6Brackets(host.Host);
        return string.Equals(hostName, "localhost", StringComparison.OrdinalIgnoreCase) ||
            (IPAddress.TryParse(hostName, out var address) && IPAddress.IsLoopback(address));
    }

    private static bool HostsMatch(string first, string second)
    {
        first = RemoveIpv6Brackets(first);
        second = RemoveIpv6Brackets(second);

        if (IPAddress.TryParse(first, out var firstAddress) &&
            IPAddress.TryParse(second, out var secondAddress))
        {
            return firstAddress.Equals(secondAddress);
        }

        return string.Equals(first, second, StringComparison.OrdinalIgnoreCase);
    }

    private static string RemoveIpv6Brackets(string host)
        => host.Length >= 2 && host[0] == '[' && host[^1] == ']'
            ? host[1..^1]
            : host;

    private static bool IsStateChanging(string method)
        => !HttpMethods.IsGet(method) &&
            !HttpMethods.IsHead(method) &&
            !HttpMethods.IsOptions(method) &&
            !HttpMethods.IsTrace(method);

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
