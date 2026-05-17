// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Threading;
using System.Threading.Tasks;
using Azure.AI.ContentUnderstanding;

namespace Microsoft.Agents.AI.AzureAI.ContentUnderstanding;

/// <summary>
/// Drives a still-in-flight Content Understanding LRO to terminal state on a background task
/// once the foreground attempt has exceeded <c>MaxWait</c>. Mutates
/// <see cref="ContentUnderstandingProviderState.Documents"/> directly through the
/// <see cref="System.Collections.Concurrent.ConcurrentDictionary{TKey, TValue}"/>; the
/// <c>AgentSessionStateBag</c> caches the live state instance, so the next turn's
/// <c>GetOrInitializeState</c> observes the runner's mutation.
/// </summary>
internal sealed class BackgroundAnalysisRunner
{
    /// <summary>
    /// Starts a fire-and-forget polling task for one document. The returned <see cref="Task"/>
    /// completes whether the LRO finishes, the runner observes cancellation, or any exception
    /// is raised — the runner never propagates exceptions to the unobserved-task channel.
    /// </summary>
    /// <param name="documentKey">Key of the <see cref="DocumentEntry"/> the runner will update.</param>
    /// <param name="continuation">Callback that resumes the LRO. Must run to terminal state or honor <paramref name="ct"/>.</param>
    /// <param name="state">Live provider state to mutate in place.</param>
    /// <param name="sections">Output sections used when rendering the completed analysis.</param>
    /// <param name="fileSearchConfig">When non-<see langword="null"/>, the runner additionally renders the document's vector-store search payload and stamps it on <see cref="DocumentEntry.SearchPayload"/> so a later <c>InvokingCoreAsync</c> turn can promote it without keeping the raw <see cref="AnalysisResult"/> alive.</param>
    /// <param name="ct">Token cancelled when the owning provider is disposed.</param>
    public Task StartAsync(
        string documentKey,
        Func<CancellationToken, Task<AnalysisOutcome>> continuation,
        ContentUnderstandingProviderState state,
        AnalysisSection sections,
        FileSearchConfig? fileSearchConfig,
        CancellationToken ct)
    {
        _ = documentKey ?? throw new ArgumentNullException(nameof(documentKey));
        _ = continuation ?? throw new ArgumentNullException(nameof(continuation));
        _ = state ?? throw new ArgumentNullException(nameof(state));

        return Task.Run(async () =>
        {
            try
            {
                AnalysisOutcome outcome = await continuation(ct).ConfigureAwait(false);
                ApplyOutcome(state, documentKey, sections, fileSearchConfig, outcome);
            }
            catch (OperationCanceledException)
            {
                // Provider disposing — leave entry in Analyzing state. No status mutation.
            }
            catch (Exception ex)
            {
                ApplyFailure(state, documentKey, ex.Message);
            }
        }, ct);
    }

    private static void ApplyOutcome(
        ContentUnderstandingProviderState state,
        string documentKey,
        AnalysisSection sections,
        FileSearchConfig? fileSearchConfig,
        AnalysisOutcome outcome)
    {
        if (!state.Documents.TryGetValue(documentKey, out DocumentEntry? existing) || existing is null)
        {
            // Foreground flow should always have created the entry before spawning us; if it
            // somehow vanished there is nothing to update.
            return;
        }

        DocumentEntry next;
        if (outcome.Completed && outcome.Result is not null)
        {
            string rendered = AnalysisRenderer.Render(outcome.Result, existing.Filename, sections);
            string markdownOnly = AnalysisRenderer.Render(outcome.Result, existing.Filename, AnalysisSection.Markdown);
            string? searchPayload = AnalysisRenderer.RenderSearchPayload(
                outcome.Result, existing.Filename, AnalysisSection.Markdown, fileSearchConfig);
            next = existing with
            {
                Status = DocumentStatus.Ready,
                Result = rendered,
                MarkdownResult = markdownOnly,
                SearchPayload = searchPayload,
                AnalyzedAt = DateTimeOffset.UtcNow,
                AnalysisDuration = outcome.Duration,
                OperationId = null,
                Error = null,
            };
        }
        else if (outcome.Error is not null)
        {
            next = existing with
            {
                Status = DocumentStatus.Failed,
                Error = outcome.Error.Message,
                AnalysisDuration = outcome.Duration,
            };
        }
        else
        {
            // Non-terminal outcome — continuation contract says this shouldn't happen, but
            // never overwrite a perfectly good Analyzing entry with a worse one.
            return;
        }

        state.Documents[documentKey] = next;
    }

    private static void ApplyFailure(
        ContentUnderstandingProviderState state,
        string documentKey,
        string errorMessage)
    {
        if (!state.Documents.TryGetValue(documentKey, out DocumentEntry? existing) || existing is null)
        {
            return;
        }

        state.Documents[documentKey] = existing with
        {
            Status = DocumentStatus.Failed,
            Error = errorMessage,
        };
    }
}
