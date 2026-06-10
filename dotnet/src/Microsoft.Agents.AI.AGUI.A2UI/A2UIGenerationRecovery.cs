// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Text.Json.Nodes;
using System.Threading;
using System.Threading.Tasks;

namespace Microsoft.Agents.AI.AGUI.A2UI;

/// <summary>
/// One attempt of the A2UI validate-and-retry generation loop.
/// </summary>
/// <param name="Attempt">The 1-based attempt number.</param>
/// <param name="Ok">Whether the attempt produced a valid component tree.</param>
/// <param name="Errors">The validation errors when <paramref name="Ok"/> is <see langword="false"/>.</param>
public sealed record A2UIAttemptRecord(int Attempt, bool Ok, IReadOnlyList<A2UIValidationError> Errors);

/// <summary>
/// Configuration for the A2UI generation recovery loop.
/// </summary>
public sealed class A2UIRecoveryConfig
{
    /// <summary>
    /// Gets the maximum number of generation attempts. Defaults to
    /// <see cref="A2UIConstants.MaxA2UIAttempts"/> when unset.
    /// </summary>
    public int? MaxAttempts { get; init; }
}

/// <summary>
/// The outcome of the A2UI generation recovery loop.
/// </summary>
/// <param name="Envelope">
/// The operations envelope on success, or a structured hard-failure envelope
/// (<c>code: "a2ui_recovery_exhausted"</c>) when all attempts failed.
/// </param>
/// <param name="Attempts">The per-attempt records, in order.</param>
/// <param name="Ok">Whether a valid surface was produced.</param>
public sealed record A2UIRecoveryResult(string Envelope, IReadOnlyList<A2UIAttemptRecord> Attempts, bool Ok);

/// <summary>
/// The A2UI validate-and-retry generation loop, mirroring
/// <c>runA2UIGenerationWithRecovery</c> / <c>run_a2ui_generation_with_recovery</c> in the sibling toolkits.
/// </summary>
/// <remarks>
/// Each attempt invokes the subagent, validates the structured tool output, and either
/// returns the built envelope (first valid attempt wins) or retries with the prior
/// attempt's errors appended to the prompt. A missing tool call counts as a failed,
/// retryable attempt. After the attempt cap is reached, a structured hard-failure
/// envelope is returned instead of throwing, so the conversation stays usable.
/// </remarks>
public static class A2UIGenerationRecovery
{
    /// <summary>
    /// Formats validation errors as a compact, model-readable list
    /// (<c>- [code] path: message</c> per line).
    /// </summary>
    /// <param name="errors">The errors to format.</param>
    /// <returns>The formatted block.</returns>
    public static string FormatValidationErrors(IEnumerable<A2UIValidationError> errors)
        => throw new NotImplementedException();

    /// <summary>
    /// Appends a fix-it block carrying <paramref name="errors"/> to <paramref name="prompt"/>.
    /// Returns the prompt unchanged when there are no errors.
    /// </summary>
    /// <param name="prompt">The base subagent prompt.</param>
    /// <param name="errors">The prior attempt's validation errors.</param>
    /// <returns>The augmented prompt.</returns>
    public static string AugmentPromptWithValidationErrors(string prompt, IReadOnlyList<A2UIValidationError> errors)
        => throw new NotImplementedException();

    /// <summary>
    /// Runs the validate-and-retry loop until a valid surface is produced or the attempt cap is reached.
    /// </summary>
    /// <param name="basePrompt">The subagent system prompt produced by request preparation.</param>
    /// <param name="invokeSubagentAsync">
    /// Invokes the subagent with the (possibly error-augmented) prompt and the 1-based attempt
    /// number, returning the structured <c>render_a2ui</c> tool arguments, or <see langword="null"/>
    /// when the model did not call the tool.
    /// </param>
    /// <param name="buildEnvelope">Builds the final operations envelope from validated tool arguments.</param>
    /// <param name="catalog">The catalog used for semantic validation, when available.</param>
    /// <param name="config">Loop configuration overrides.</param>
    /// <param name="onAttempt">Observability callback invoked after each attempt is validated.</param>
    /// <param name="cancellationToken">A token to cancel the loop between attempts.</param>
    /// <returns>The loop outcome.</returns>
    public static Task<A2UIRecoveryResult> RunAsync(
        string basePrompt,
        Func<string, int, CancellationToken, ValueTask<JsonObject?>> invokeSubagentAsync,
        Func<JsonObject, string> buildEnvelope,
        A2UIValidationCatalog? catalog = null,
        A2UIRecoveryConfig? config = null,
        Action<A2UIAttemptRecord>? onAttempt = null,
        CancellationToken cancellationToken = default)
        => throw new NotImplementedException();
}
