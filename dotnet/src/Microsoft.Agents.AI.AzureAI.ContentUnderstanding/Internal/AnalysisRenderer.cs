// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Text.RegularExpressions;
using Azure.AI.ContentUnderstanding;

namespace Microsoft.Agents.AI.AzureAI.ContentUnderstanding;

/// <summary>
/// Converts a Content Understanding <see cref="AnalysisResult"/> into the LLM-ready Markdown block
/// injected into the agent context, plus the alternate payload uploaded to a file-search vector
/// store. Mirrors Python <c>_render_for_llm</c> / <c>_render_search_payload</c>.
/// </summary>
/// <remarks>
/// Delegates to <see cref="LlmInputHelper.ToLlmInput(AnalysisResult, IDictionary{string, object}, LlmInputOptions)"/>
/// for the actual rendering. After rendering, strips spurious telemetry lines of the form
/// <c>- LLMStats: ...</c> that the SDK occasionally leaks into the <c>rai_warnings:</c> YAML list
/// (decision C1 / Python <c>_RAI_TELEMETRY_LINE_RE</c>).
/// </remarks>
internal static class AnalysisRenderer
{
    // Multi-line regex matching "- LLMStats: ..." entries inside the rai_warnings YAML list.
    // Mirrors Python _RAI_TELEMETRY_LINE_RE exactly: ^[ \t]*-[ \t]+LLMStats:.*(?:\r?\n|$)
    private static readonly Regex s_telemetryLineRegex = new(
        @"^[ \t]*-[ \t]+LLMStats:.*(?:\r?\n|$)",
        RegexOptions.Multiline | RegexOptions.CultureInvariant);

    public static string Render(
        AnalysisResult result,
        string filename,
        AnalysisSection sections,
        bool? includeFieldsOverride = null)
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
            IncludeFields = includeFieldsOverride ?? ((sections & AnalysisSection.Fields) != 0),
        };

        string rendered = result.ToLlmInput(metadata, options);
        return StripTelemetry(rendered);
    }

    public static string? RenderSearchPayload(
        AnalysisResult result,
        string filename,
        AnalysisSection sections,
        FileSearchConfig? config)
    {
        if (config is null)
        {
            return null;
        }

        return Render(result, filename, sections, includeFieldsOverride: config.IncludeFields);
    }

    /// <summary>
    /// Removes <c>- LLMStats: ...</c> telemetry lines from an already-rendered block.
    /// Exposed <c>internal</c> for direct regex coverage in unit tests.
    /// </summary>
    internal static string StripTelemetry(string rendered)
        => string.IsNullOrEmpty(rendered) ? rendered : s_telemetryLineRegex.Replace(rendered, string.Empty);
}
