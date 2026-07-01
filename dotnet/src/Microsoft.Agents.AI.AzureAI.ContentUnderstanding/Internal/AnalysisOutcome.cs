// Copyright (c) Microsoft. All rights reserved.

using Azure.AI.ContentUnderstanding;

namespace Microsoft.Agents.AI.AzureAI.ContentUnderstanding;

/// <summary>
/// Result of one Content Understanding analysis attempt — either a fresh submission or a
/// re-poll of a previously-timed-out operation.
/// </summary>
/// <remarks>
/// <para><see cref="Completed"/> distinguishes three outcomes:</para>
/// <list type="bullet">
///   <item><description>Completed and successful: <c>Completed = true</c>, <see cref="Result"/> is set.</description></item>
///   <item><description>Failed terminally: <c>Completed = false</c>, <see cref="Error"/> is set.</description></item>
///   <item>
///     <description>
///       Inline timeout (operation still running on the service): <c>Completed = false</c>,
///       <see cref="Error"/> is null. When <see cref="RehydrationTokenJson"/> is non-null the
///       provider will re-poll the operation on the next turn via
///       <c>Operation.Rehydrate&lt;AnalysisResult&gt;</c>; otherwise the entry stays in
///       <c>Analyzing</c> with no way to resume.
///     </description>
///   </item>
/// </list>
/// </remarks>
internal sealed record AnalysisOutcome(
    bool Completed,
    AnalysisResult? Result,
    string? OperationId,
    Exception? Error,
    TimeSpan Duration)
{
    /// <summary>
    /// JSON-serialized <see cref="Azure.Core.RehydrationToken"/> captured at timeout. The
    /// provider uses this on the next turn to reconstruct the <c>Operation&lt;AnalysisResult&gt;</c>
    /// via <c>Operation.Rehydrate&lt;AnalysisResult&gt;(pipeline, token, options)</c> without
    /// resubmitting the original binary payload. Null when no resumption is possible.
    /// </summary>
    public string? RehydrationTokenJson { get; init; }
}
