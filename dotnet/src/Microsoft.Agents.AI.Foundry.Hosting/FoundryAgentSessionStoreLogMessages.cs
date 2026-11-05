// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Diagnostics.CodeAnalysis;
using Microsoft.Extensions.Logging;

namespace Microsoft.Agents.AI.Foundry.Hosting;

/// <summary>
/// Source-generated logging for <see cref="FoundryAgentSessionStore"/>.
/// </summary>
[ExcludeFromCodeCoverage]
internal static partial class FoundryAgentSessionStoreLogMessages
{
    [LoggerMessage(LogLevel.Debug, "Session '{SessionId}' was not found in the Foundry state store '{StoreName}'. Nothing to delete.")]
    public static partial void LogSessionNotFound(
        this ILogger logger,
        string sessionId,
        string storeName,
        Exception exception);
}
