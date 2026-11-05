// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Diagnostics.CodeAnalysis;
using Microsoft.Extensions.Logging;

namespace Microsoft.Agents.AI.Foundry.Hosting;

/// <summary>
/// Source-generated logging for <see cref="AgentFrameworkResponseHandler"/>.
/// </summary>
[ExcludeFromCodeCoverage]
internal static partial class AgentFrameworkResponseHandlerLogMessages
{
    [LoggerMessage(LogLevel.Error, "Agent execution failed for response {ResponseId}.")]
    public static partial void LogAgentExecutionFailed(
        this ILogger logger,
        string responseId,
        Exception exception);

    [LoggerMessage(LogLevel.Information, "Shutdown detected on a resilient turn; deferring for recovery.")]
    public static partial void LogShutdownDeferredForRecovery(this ILogger logger);

    [LoggerMessage(LogLevel.Information, "Shutdown detected, emitting incomplete response.")]
    public static partial void LogShutdownEmittingIncomplete(this ILogger logger);

    [LoggerMessage(LogLevel.Information, "Steering input detected for response {ResponseId}; completing the active turn.")]
    public static partial void LogSteeringInputDetected(this ILogger logger, string responseId);

    [LoggerMessage(LogLevel.Debug, "Incremental session save was skipped for response {ResponseId}; the end-of-turn save will persist the final state.")]
    public static partial void LogIncrementalSessionSaveSkipped(
        this ILogger logger,
        string responseId,
        Exception exception);

    [LoggerMessage(LogLevel.Error, "Agent '{AgentName}' should not have server side storage enabled. This produced a new untracked conversation/response in the server while the hosted agent also generated a conversation for the request of the agent.")]
    public static partial void LogServerSideStorageNotAllowed(this ILogger logger, string? agentName);

    [LoggerMessage(LogLevel.Debug, "Workflow checkpoint {CheckpointId} was not paired with response {ResponseId} because its AgentSession could not be saved.")]
    public static partial void LogWorkflowCheckpointNotPaired(
        this ILogger logger,
        string checkpointId,
        string responseId,
        Exception exception);

    [LoggerMessage(LogLevel.Warning, "Foundry toolbox '{ToolboxName}' could not be resolved for response {ResponseId}.")]
    public static partial void LogToolboxResolutionFailed(
        this ILogger logger,
        string toolboxName,
        string responseId,
        Exception exception);

    [LoggerMessage(LogLevel.Warning, "OAuth consent request for tool '{ToolName}' in toolbox '{ToolboxName}' was rejected by the consent link policy for response {ResponseId}.")]
    public static partial void LogConsentLinkRejected(
        this ILogger logger,
        string toolName,
        string toolboxName,
        string responseId);

    [LoggerMessage(LogLevel.Warning, "Agent '{AgentName}' not found in keyed services. Attempting default resolution.")]
    public static partial void LogKeyedAgentNotFound(this ILogger logger, string agentName);

    [LoggerMessage(LogLevel.Warning, "SessionStore for agent '{AgentName}' not found in keyed services. Attempting default resolution.")]
    public static partial void LogKeyedSessionStoreNotFound(this ILogger logger, string agentName);
}
