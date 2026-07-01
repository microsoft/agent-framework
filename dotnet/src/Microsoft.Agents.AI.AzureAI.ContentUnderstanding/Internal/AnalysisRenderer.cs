// Copyright (c) Microsoft. All rights reserved.

using Azure.AI.ContentUnderstanding;

namespace Microsoft.Agents.AI.AzureAI.ContentUnderstanding;

/// <summary>
/// Converts a Content Understanding <see cref="AnalysisResult"/> into the LLM-ready Markdown block
/// injected into the agent context (also used verbatim for the file-search vector-store upload).
/// </summary>
/// <remarks>
/// Delegates to <see cref="LlmInputHelper.ToLlmInput(AnalysisResult, IDictionary{string, object}, LlmInputOptions)"/>
/// for the actual rendering. Filtering of spurious <c>LLMStats:</c> telemetry from the
/// <c>rai_warnings:</c> block is handled upstream by the SDK helper
/// (<c>Azure.AI.ContentUnderstanding</c> >= 1.2.0-beta.2).
/// </remarks>
internal static class AnalysisRenderer
{
    public static string Render(
        AnalysisResult result,
        string filename,
        AnalysisSection sections)
    {
        if (result is null)
        {
            throw new ArgumentNullException(nameof(result));
        }

        if (string.IsNullOrEmpty(filename))
        {
            throw new ArgumentException("Filename must not be null or empty.", nameof(filename));
        }

        Dictionary<string, object> metadata = new(StringComparer.Ordinal)
        {
            ["source"] = filename,
        };

        LlmInputOptions options = new()
        {
            IncludeMarkdown = (sections & AnalysisSection.Markdown) != 0,
            IncludeFields = (sections & AnalysisSection.Fields) != 0,
        };

        return result.ToLlmInput(metadata, options);
    }
}
