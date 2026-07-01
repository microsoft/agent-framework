// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.AzureAI.ContentUnderstanding;

/// <summary>
/// Compact summary surfaced by the <c>list_documents</c> tool.
/// </summary>
internal sealed record DocumentSummary(
    string Filename,
    DocumentStatus Status,
    string MediaType,
    string AnalyzerId,
    DateTimeOffset? AnalyzedAt,
    int? SizeBytes);

/// <summary>
/// Builds the auto-registered <see cref="AIFunction"/>s surfaced by
/// <see cref="ContentUnderstandingContextProvider"/> in <c>AIContext.Tools</c>. Both factories
/// take a <c>stateAccessor</c> delegate so the returned <see cref="AIFunction"/> reflects the
/// live document registry (including background-runner promotions) for the session it was built
/// for. The provider rebuilds these tools each turn bound to that turn's per-session state, so a
/// single provider instance shared across concurrent sessions never crosses registries.
/// </summary>
internal static class ToolFactory
{
    /// <summary>Tool name advertised to the LLM.</summary>
    internal const string ListDocumentsToolName = "list_documents";

    /// <summary>Tool name advertised to the LLM.</summary>
    internal const string GetAnalyzedDocumentToolName = "get_analyzed_document";

    /// <summary>Tool description advertised to the LLM.</summary>
    internal const string ListDocumentsDescription =
        "List all documents that have been uploaded in this session with their analysis status " +
        "(analyzing, uploading, ready, or failed).";

    /// <summary>
    /// Tool description; deliberately instructs the LLM to prefer auto-injected content first
    /// and fall back to this tool only when content has been evicted or filtered.
    /// </summary>
    internal const string GetAnalyzedDocumentDescription =
        "Retrieve the rendered text of a previously analyzed document by filename. Prefer the " +
        "auto-injected document blocks when present; call this tool only when the desired " +
        "content is no longer visible in the conversation. Returns the rendered markdown " +
        "(and structured fields when section=Default) or an error string when the document is " +
        "not yet ready or unknown.";

    public static AIFunction CreateListDocumentsTool(Func<ContentUnderstandingProviderState?> stateAccessor)
    {
        _ = stateAccessor ?? throw new ArgumentNullException(nameof(stateAccessor));

        IReadOnlyList<DocumentSummary> ListDocuments()
        {
            ContentUnderstandingProviderState? state = stateAccessor();
            if (state?.Documents is not { IsEmpty: false } documents)
            {
                return Array.Empty<DocumentSummary>();
            }

            // Snapshot the registry before enumeration: the background runner may promote/add
            // entries concurrently, so iterating a live view could observe a torn state (or, if
            // the backing store were ever a plain Dictionary, throw "Collection was modified").
            KeyValuePair<string, DocumentEntry>[] snapshot = documents.ToArray();
            List<DocumentSummary> summaries = new(snapshot.Length);
            foreach (KeyValuePair<string, DocumentEntry> kvp in snapshot)
            {
                DocumentEntry entry = kvp.Value;
                summaries.Add(new DocumentSummary(
                    Filename: entry.Filename,
                    Status: entry.Status,
                    MediaType: entry.MediaType,
                    AnalyzerId: entry.AnalyzerId,
                    AnalyzedAt: entry.AnalyzedAt,
                    SizeBytes: entry.SizeBytes));
            }
            return summaries;
        }

        return AIFunctionFactory.Create(
            ListDocuments,
            name: ListDocumentsToolName,
            description: ListDocumentsDescription);
    }

    public static AIFunction CreateGetAnalyzedDocumentTool(Func<ContentUnderstandingProviderState?> stateAccessor)
    {
        _ = stateAccessor ?? throw new ArgumentNullException(nameof(stateAccessor));

        string GetAnalyzedDocument(string documentName, AnalysisSection section = AnalysisSection.Default)
        {
            if (string.IsNullOrEmpty(documentName))
            {
                return "Document name is required";
            }

            ContentUnderstandingProviderState? state = stateAccessor();
            if (state is null || !state.Documents.TryGetValue(documentName, out DocumentEntry? entry) || entry is null)
            {
                return $"Document '{documentName}' not found";
            }

            if (entry.Status != DocumentStatus.Ready)
            {
                return $"Document '{documentName}' is still {entry.Status}";
            }

            // Only Markdown and Default are supported; any other (e.g. out-of-range) value is
            // treated as Default. Markdown-only section requested → return the pre-rendered
            // markdown-only payload (no fields block). Falls back to the full payload if the
            // markdown-only variant wasn't stored (e.g. provider configured with OutputSections
            // excluding Markdown).
            if (section == AnalysisSection.Markdown && entry.MarkdownResult is not null)
            {
                return entry.MarkdownResult;
            }

            return entry.Result ?? string.Empty;
        }

        return AIFunctionFactory.Create(
            GetAnalyzedDocument,
            name: GetAnalyzedDocumentToolName,
            description: GetAnalyzedDocumentDescription);
    }
}
