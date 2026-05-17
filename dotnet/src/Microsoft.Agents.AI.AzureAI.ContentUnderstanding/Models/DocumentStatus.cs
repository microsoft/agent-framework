// Copyright (c) Microsoft. All rights reserved.

namespace Microsoft.Agents.AI.AzureAI.ContentUnderstanding;

/// <summary>
/// Lifecycle status of a document tracked by <see cref="ContentUnderstandingContextProvider"/>.
/// </summary>
/// <remarks>
/// See <c>features/sdk/dotnet-cu-context-provider/design-doc-dotnet-cu-context-provider.md</c>
/// "Data Model" for the full lifecycle.
/// </remarks>
public enum DocumentStatus
{
    /// <summary>Analysis is in progress (Content Understanding LRO not yet terminal).</summary>
    Analyzing,

    /// <summary>Analysis completed; rendered payload is being uploaded to a vector store (only when <c>FileSearchConfig</c> is configured).</summary>
    Uploading,

    /// <summary>Analysis (and upload, when applicable) completed successfully and the document is available to the agent.</summary>
    Ready,

    /// <summary>Analysis or upload failed terminally; <c>DocumentEntry.Error</c> carries the reason.</summary>
    Failed,
}
