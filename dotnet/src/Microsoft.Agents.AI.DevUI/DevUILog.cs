// Copyright (c) Microsoft. All rights reserved.

using System.Net;

namespace Microsoft.Agents.AI.DevUI;

internal static partial class DevUILog
{
    [LoggerMessage(
        EventId = 1,
        Level = LogLevel.Warning,
        Message = "Rejected non-loopback DevUI request from {RemoteIp}. Set DevUIOptions.AllowRemoteAccess to permit remote callers.")]
    public static partial void RejectedNonLoopbackRequest(ILogger logger, IPAddress? remoteIp);

    [LoggerMessage(
        EventId = 2,
        Level = LogLevel.Warning,
        Message = "DevUI is configured with AllowRemoteAccess=true and no authentication. Set DevUIOptions.AuthToken, the {EnvVar} environment variable, or attach an authorization policy via ConfigureEndpoints.")]
    public static partial void InsecurelyExposed(ILogger logger, string envVar);
}
