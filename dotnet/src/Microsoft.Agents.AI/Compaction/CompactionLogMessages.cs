// Copyright (c) Microsoft. All rights reserved.

using System.Diagnostics.CodeAnalysis;
using Microsoft.Extensions.Logging;

namespace Microsoft.Agents.AI.Compaction;

#pragma warning disable SYSLIB1006 // Multiple logging methods cannot use the same event id within a class

/// <summary>
/// Extensions for logging compaction diagnostics.
/// </summary>
/// <remarks>
/// This extension uses the <see cref="LoggerMessageAttribute"/> to
/// generate logging code at compile time to achieve optimized code.
/// </remarks>
[ExcludeFromCodeCoverage]
internal static partial class CompactionLogMessages
{
    /// <summary>
    /// Logs when compaction is skipped because the trigger condition was not met.
    /// </summary>
    [LoggerMessage(
        Level = LogLevel.Trace,
        Message = "Compaction skipped for {StrategyName}: trigger condition not met or insufficient groups.")]
    public static partial void LogCompactionSkipped(
        this ILogger logger,
        string strategyName);

    /// <summary>
    /// Logs compaction completion with before/after metrics.
    /// </summary>
    [LoggerMessage(
        Level = LogLevel.Debug,
        Message = "Compaction completed: {StrategyName} in {DurationMs}ms — Messages {BeforeMessages}→{AfterMessages}, Groups {BeforeGroups}→{AfterGroups}, Tokens {BeforeTokens}→{AfterTokens}")]
    public static partial void LogCompactionCompleted(
        this ILogger logger,
        string strategyName,
        long durationMs,
        int beforeMessages,
        int afterMessages,
        int beforeGroups,
        int afterGroups,
        int beforeTokens,
        int afterTokens);

    /// <summary>
    /// Logs when the compaction provider skips compaction.
    /// </summary>
    [LoggerMessage(
        Level = LogLevel.Trace,
        Message = "CompactionProvider skipped: {Reason}.")]
    public static partial void LogCompactionProviderSkipped(
        this ILogger logger,
        string reason);

    /// <summary>
    /// Logs when the compaction provider begins applying a compaction strategy.
    /// </summary>
    [LoggerMessage(
        Level = LogLevel.Debug,
        Message = "CompactionProvider applying compaction to {MessageCount} messages using {StrategyName}.")]
    public static partial void LogCompactionProviderApplying(
        this ILogger logger,
        int messageCount,
        string strategyName);

    /// <summary>
    /// Logs when the compaction provider has applied compaction with result metrics.
    /// </summary>
    [LoggerMessage(
        Level = LogLevel.Debug,
        Message = "CompactionProvider compaction applied: messages {BeforeMessages}→{AfterMessages}.")]
    public static partial void LogCompactionProviderApplied(
        this ILogger logger,
        int beforeMessages,
        int afterMessages);

    /// <summary>
    /// Logs when a summarization LLM call is starting.
    /// </summary>
    [LoggerMessage(
        Level = LogLevel.Debug,
        Message = "Summarization starting for {GroupCount} groups ({MessageCount} messages) using {ChatClientType}.")]
    public static partial void LogSummarizationStarting(
        this ILogger logger,
        int groupCount,
        int messageCount,
        string chatClientType);

    /// <summary>
    /// Logs when a summarization LLM call has completed.
    /// </summary>
    [LoggerMessage(
        Level = LogLevel.Debug,
        Message = "Summarization completed: summary length {SummaryLength} characters, inserted at index {InsertIndex}.")]
    public static partial void LogSummarizationCompleted(
        this ILogger logger,
        int summaryLength,
        int insertIndex);

    /// <summary>
    /// Logs when a summarization LLM call fails and groups are restored.
    /// </summary>
    [LoggerMessage(
        Level = LogLevel.Warning,
        Message = "Summarization failed for {GroupCount} groups; restoring excluded groups and continuing without compaction. Error: {ErrorMessage}")]
    public static partial void LogSummarizationFailed(
        this ILogger logger,
        int groupCount,
        string errorMessage);
}
