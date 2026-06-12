// Copyright (c) Microsoft. All rights reserved.

namespace Microsoft.Agents.AI.AzureAI.ContentUnderstanding;

/// <summary>
/// One tracked document in the provider's session state.
/// </summary>
/// <remarks>
/// Persisted via <c>AgentSession.StateBag</c> and serialized with <c>System.Text.Json</c>; all
/// properties use simple JSON-friendly types (no <c>byte[]</c>, no <c>Stream</c>).
/// See <c>features/sdk/dotnet-cu-context-provider/design-doc-dotnet-cu-context-provider.md</c>
/// "Data Model".
/// </remarks>
internal sealed record DocumentEntry
{
    /// <summary>Stable per-document key (currently the resolved filename; same as <see cref="Filename"/> in v1).</summary>
    public string DocumentKey { get; init; } = string.Empty;

    /// <summary>The resolved filename used to identify the document in tool responses.</summary>
    public string Filename { get; init; } = string.Empty;

    /// <summary>
    /// <see cref="Filename"/> with CommonMark-significant characters (<c>_ * ` [ ]</c>) replaced
    /// by <c>-</c>. Used wherever the filename surfaces in LLM-facing strings (vector-store upload
    /// name, file-search status notes); <see cref="Filename"/> stays original for state keys, dedup,
    /// and logs. Filenames like <c>mixed_financial_invoices.pdf</c> would otherwise render with
    /// the underscores treated as italics by chat UIs.
    /// </summary>
    public string MarkdownSafeName => SanitizeForMarkdown(this.Filename);

    /// <summary>
    /// Replaces CommonMark-significant characters (<c>_ * ` [ ]</c>) in <paramref name="s"/> with <c>-</c>.
    /// Exposed at <see langword="internal"/> scope so the provider can sanitize raw attachment
    /// filenames before they reach the model on code paths that do not yet have a
    /// <see cref="DocumentEntry"/> (e.g. duplicate-upload rejection notes).
    /// </summary>
    internal static string SanitizeForMarkdown(string s)
    {
        if (string.IsNullOrEmpty(s))
        {
            return s;
        }

        for (int i = 0; i < s.Length; i++)
        {
            char c = s[i];
            if (c is '_' or '*' or '`' or '[' or ']')
            {
                return s
                    .Replace('_', '-')
                    .Replace('*', '-')
                    .Replace('`', '-')
                    .Replace('[', '-')
                    .Replace(']', '-');
            }
        }

        return s;
    }

    /// <summary>The resolved media type (e.g. <c>application/pdf</c>, <c>audio/mpeg</c>).</summary>
    public string MediaType { get; init; } = string.Empty;

    /// <summary>The Content Understanding analyzer id used for this document.</summary>
    public string AnalyzerId { get; init; } = string.Empty;

    /// <summary>Current lifecycle status.</summary>
    public DocumentStatus Status { get; init; }

    /// <summary>When the analysis reached terminal success; <see langword="null"/> while still <see cref="DocumentStatus.Analyzing"/>.</summary>
    public DateTimeOffset? AnalyzedAt { get; init; }

    /// <summary>Wall-clock duration of the analysis call; <see langword="null"/> while still analyzing.</summary>
    public TimeSpan? AnalysisDuration { get; init; }

    /// <summary>Wall-clock duration of the vector-store upload (only when <c>FileSearchConfig</c> is set); otherwise <see langword="null"/>.</summary>
    public TimeSpan? UploadDuration { get; init; }

    /// <summary>Rendered LLM-facing text (markdown + YAML front-matter) once <see cref="Status"/> is <see cref="DocumentStatus.Ready"/>.</summary>
    public string? Result { get; init; }

    /// <summary>
    /// Alternate rendering with the structured-fields block omitted — used by
    /// <c>get_analyzed_document</c> when called with <see cref="AnalysisSection.Markdown"/>.
    /// </summary>
    public string? MarkdownResult { get; init; }

    /// <summary>Error message when <see cref="Status"/> is <see cref="DocumentStatus.Failed"/>.</summary>
    public string? Error { get; init; }

    /// <summary>Content Understanding operation identifier; surfaces to <c>list_documents</c> for diagnostics. Populated when an analysis is in flight or has completed.</summary>
    public string? OperationId { get; init; }

    /// <summary>
    /// JSON-serialized <see cref="Azure.Core.RehydrationToken"/> for the in-flight Content
    /// Understanding LRO when <see cref="Status"/> is <see cref="DocumentStatus.Analyzing"/>.
    /// The next turn's <c>InvokingCoreAsync</c> rebuilds the operation via
    /// <c>Operation.Rehydrate&lt;AnalysisResult&gt;</c> and polls it for up to <c>MaxWait</c>;
    /// cleared once the operation reaches a terminal state.
    /// </summary>
    public string? RehydrationTokenJson { get; init; }

    /// <summary>
    /// File identifier returned by <c>FileSearchBackend.UploadAsync</c> after this document was
    /// uploaded into a vector store; <see langword="null"/> when no <c>FileSearchConfig</c> is
    /// configured or the document was not uploaded (e.g. empty payload, failure).
    /// </summary>
    /// <remarks>
    /// Tracked separately from <see cref="RehydrationTokenJson"/> (which drives CU LRO
    /// resumption). Read by <c>ContentUnderstandingContextProvider.DisposeAsync</c> for cleanup.
    /// </remarks>
    public string? VectorStoreFileId { get; init; }

    /// <summary>Byte size of the original attachment when known (<c>DataContent</c>); <see langword="null"/> for <c>UriContent</c>.</summary>
    public int? SizeBytes { get; init; }
}
