// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Diagnostics.CodeAnalysis;
using Microsoft.Extensions.Logging;

namespace Microsoft.Agents.AI.Foundry.Hosting;

/// <summary>
/// Source-generated logging for <see cref="HostedStoredOutputHealthCheck"/>.
/// </summary>
[ExcludeFromCodeCoverage]
internal static partial class HostedStoredOutputHealthCheckLogMessages
{
    [LoggerMessage(LogLevel.Debug, "Could not probe the stored output setting for agent '{AgentName}'.")]
    public static partial void LogStoredOutputProbeFailed(
        this ILogger logger,
        string? agentName,
        Exception exception);

    [LoggerMessage(LogLevel.Debug, "Agent '{AgentName}' builds a request whose stored output setting could not be determined.")]
    public static partial void LogStoredOutputSettingUnknown(this ILogger logger, string? agentName);
}
