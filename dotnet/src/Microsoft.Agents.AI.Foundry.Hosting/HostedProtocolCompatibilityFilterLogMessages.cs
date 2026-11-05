// Copyright (c) Microsoft. All rights reserved.

using System.Diagnostics.CodeAnalysis;
using Microsoft.Extensions.Logging;

namespace Microsoft.Agents.AI.Foundry.Hosting;

/// <summary>
/// Source-generated logging for <see cref="HostedProtocolCompatibilityFilter"/>.
/// </summary>
[ExcludeFromCodeCoverage]
internal static partial class HostedProtocolCompatibilityFilterLogMessages
{
    [LoggerMessage(LogLevel.Error, "Hosted container served unsupported Responses protocol 1.0.0 (no x-agent-foundry-call-id header); this image requires protocol 2.0.0.")]
    public static partial void LogUnsupportedResponsesProtocol(this ILogger logger);
}
