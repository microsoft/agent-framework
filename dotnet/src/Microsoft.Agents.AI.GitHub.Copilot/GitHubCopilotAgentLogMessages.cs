// Copyright (c) Microsoft. All rights reserved.

using System.Diagnostics.CodeAnalysis;
using Microsoft.Extensions.Logging;

namespace Microsoft.Agents.AI.GitHub.Copilot;
#pragma warning disable SYSLIB1006 // Multiple logging methods cannot use the same event id within a class

/// <summary>
/// Extensions for logging <see cref="GitHubCopilotAgent"/> invocations.
/// </summary>
/// <remarks>
/// This extension uses the <see cref="LoggerMessageAttribute"/> to
/// generate logging code at compile time to achieve optimized code.
/// </remarks>
[ExcludeFromCodeCoverage]
internal static partial class GitHubCopilotAgentLogMessages
{
    /// <summary>
    /// Logs a warning when a custom <c>OnPreToolUse</c> hook is present and approval-gating will not be applied automatically.
    /// </summary>
    [LoggerMessage(
        Level = LogLevel.Warning,
        Message = "A custom 'OnPreToolUse' hook is configured on the SessionConfig, so {Count} approval-required tool(s) ({Tools}) " +
                  "will not be automatically gated by GitHubCopilotAgent. The custom hook is responsible for enforcing approval " +
                  "(for example, by returning a 'deny' or 'ask' PreToolUseHookOutput).")]
    public static partial void LogApprovalGatingSkippedDueToCustomHook(
        this ILogger logger,
        int count,
        string tools);
}
