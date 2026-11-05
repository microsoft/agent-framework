// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Diagnostics.CodeAnalysis;
using Microsoft.Extensions.Logging;

namespace Microsoft.Agents.AI.Foundry.Hosting;

/// <summary>
/// Source-generated logging for <see cref="FoundryToolboxService"/>.
/// </summary>
[ExcludeFromCodeCoverage]
internal static partial class FoundryToolboxServiceLogMessages
{
    [LoggerMessage(LogLevel.Warning, "Neither FOUNDRY_PROJECT_ENDPOINT nor AZURE_AI_PROJECT_ENDPOINT is set; toolbox support is disabled.")]
    public static partial void LogToolboxSupportDisabled(this ILogger logger);

    [LoggerMessage(LogLevel.Information, "No pre-registered toolbox names configured.")]
    public static partial void LogNoPreRegisteredToolboxes(this ILogger logger);

    [LoggerMessage(LogLevel.Information, "Toolbox '{ToolboxName}' requires user OAuth consent before its tools can be enumerated. The container stays ready; the consent prompt is surfaced to the caller per-request.")]
    public static partial void LogToolboxRequiresConsent(this ILogger logger, string toolboxName);

    [LoggerMessage(LogLevel.Warning, "Toolbox '{ToolboxName}' could not be enumerated at startup; deferring it to per-request resolution. The container stays ready and the toolbox is retried on the next request when the per-user context is available.")]
    public static partial void LogToolboxStartupEnumerationDeferred(
        this ILogger logger,
        string toolboxName,
        Exception exception);

    [LoggerMessage(LogLevel.Warning, "Retry of consent-gated toolbox '{ToolboxName}' failed; it remains pending.")]
    public static partial void LogConsentGatedToolboxRetryFailed(
        this ILogger logger,
        string toolboxName,
        Exception exception);

    [LoggerMessage(LogLevel.Warning, "Retry of deferred toolbox '{ToolboxName}' failed; it remains deferred.")]
    public static partial void LogDeferredToolboxRetryFailed(
        this ILogger logger,
        string toolboxName,
        Exception exception);

    [LoggerMessage(LogLevel.Warning, "Failed to dispose {Resource} for toolbox {ToolboxName} owned by {Owner}.")]
    public static partial void LogToolboxResourceDisposalFailed(
        this ILogger logger,
        string resource,
        string toolboxName,
        string owner,
        Exception exception);

    [LoggerMessage(LogLevel.Information, "Connecting to toolbox '{ToolboxName}' at {ProxyUrl}.")]
    public static partial void LogConnectingToToolbox(
        this ILogger logger,
        string toolboxName,
        string proxyUrl);

    [LoggerMessage(LogLevel.Information, "Toolbox '{ToolboxName}': discovered {ToolCount} tool(s).")]
    public static partial void LogToolboxToolsDiscovered(
        this ILogger logger,
        string toolboxName,
        int toolCount);

    [LoggerMessage(LogLevel.Warning, "Tool '{ToolName}' in toolbox '{ToolboxName}' has an unsupported approval configuration; requiring approval for every call.")]
    public static partial void LogUnsupportedToolApprovalConfiguration(
        this ILogger logger,
        string toolName,
        string toolboxName);
}
