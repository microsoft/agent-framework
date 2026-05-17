// Copyright (c) Microsoft. All rights reserved.

namespace Microsoft.Agents.AI.AzureAI.ContentUnderstanding;

/// <summary>
/// One tracked document in the provider's session state.
/// </summary>
/// <remarks>
/// Mirrors the Python provider's per-document state dict exactly. Persisted via
/// <c>AgentSession.StateBag</c> and serialized with <c>System.Text.Json</c>; all properties
/// use simple JSON-friendly types (no <c>byte[]</c>, no <c>Stream</c>).
/// See <c>features/sdk/dotnet-cu-context-provider/design-doc-dotnet-cu-context-provider.md</c>
/// "Data Model".
/// </remarks>
internal sealed record DocumentEntry
{
    /// <summary>Stable per-document key (currently the resolved filename; same as <see cref="Filename"/> in v1).</summary>
    public string DocumentKey { get; init; } = string.Empty;

    /// <summary>The resolved filename used to identify the document in tool responses.</summary>
    public string Filename { get; init; } = string.Empty;

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

    /// <summary>Alternate rendering used for vector-store upload (typically without the fields block).</summary>
    public string? SearchPayload { get; init; }

    /// <summary>Error message when <see cref="Status"/> is <see cref="DocumentStatus.Failed"/>.</summary>
    public string? Error { get; init; }

    /// <summary>Continuation handle for an in-flight Content Understanding LRO; used to resume across turns.</summary>
    public string? OperationId { get; init; }

    /// <summary>
    /// File identifier returned by <c>FileSearchBackend.UploadAsync</c> after this document was
    /// uploaded into a vector store; <see langword="null"/> when no <c>FileSearchConfig</c> is
    /// configured or the document was not uploaded (e.g. empty payload, failure).
    /// </summary>
    /// <remarks>
    /// Tracked separately from <see cref="OperationId"/> (which is owned by the CU LRO continuation,
    /// see Phase 6). Read by <c>ContentUnderstandingContextProvider.DisposeAsync</c> for cleanup.
    /// </remarks>
    public string? VectorStoreFileId { get; init; }

    /// <summary>Byte size of the original attachment when known (<c>DataContent</c>); <see langword="null"/> for <c>UriContent</c>.</summary>
    public int? SizeBytes { get; init; }
}
