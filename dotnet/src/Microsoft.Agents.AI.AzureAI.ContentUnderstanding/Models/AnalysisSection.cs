// Copyright (c) Microsoft. All rights reserved.

namespace Microsoft.Agents.AI.AzureAI.ContentUnderstanding;

/// <summary>
/// Selects which sections of a Content Understanding analysis result are rendered into the
/// LLM-facing text payload.
/// </summary>
/// <remarks>
/// See <c>features/sdk/dotnet-cu-context-provider/design-doc-dotnet-cu-context-provider.md</c>
/// "Data Model" / "API Surface". <see cref="Default"/> mirrors the Python provider's default
/// (markdown plus structured fields).
/// </remarks>
[Flags]
public enum AnalysisSection
{
    /// <summary>No content is rendered. Mostly useful for tests and probes.</summary>
    None = 0,

    /// <summary>Include the rendered markdown body (page markers, transcripts, scene summaries).</summary>
    Markdown = 1 << 0,

    /// <summary>Include the structured fields block (analyzer-specific key/value extractions).</summary>
    Fields = 1 << 1,

    /// <summary>Default rendering: <see cref="Markdown"/> plus <see cref="Fields"/>.</summary>
    Default = Markdown | Fields,
}
