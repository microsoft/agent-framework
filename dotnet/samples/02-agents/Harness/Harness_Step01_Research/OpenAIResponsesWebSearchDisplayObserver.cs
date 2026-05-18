// Copyright (c) Microsoft. All rights reserved.

#pragma warning disable OPENAI001 // Suppress experimental API warnings for Responses API usage.

using System.Text;
using Harness.Shared.Console;
using Harness.Shared.Console.Observers;
using Microsoft.Agents.AI;
using Microsoft.Extensions.AI;
using OpenAI.Responses;

namespace SampleApp;

/// <summary>
/// Displays web search activity in the scroll area. Shows search queries,
/// page opens, and find-in-page actions as they stream in from the API.
/// </summary>
internal sealed class OpenAIResponsesWebSearchDisplayObserver : ConsoleObserver
{
    private const int MaxQueryDisplayLength = 120;

    /// <inheritdoc/>
    public override async Task OnContentAsync(IUXStateDriver ux, AIContent content, AIAgent agent, AgentSession session)
    {
        if (content is WebSearchToolResultContent resultContent
            && resultContent.RawRepresentation is WebSearchCallResponseItem wscri)
        {
            await WriteActionAsync(ux, wscri, resultContent.Outputs);
        }
    }

    private static async Task WriteActionAsync(IUXStateDriver ux, WebSearchCallResponseItem wscri, IList<AIContent>? outputs)
    {
        WebSearchAction? action = wscri.Action;
        if (action is null)
        {
            await ux.WriteInfoLineAsync("🌐 Web Search Tool (no action details)", ConsoleColor.DarkCyan);
            return;
        }

        switch (action)
        {
            case WebSearchFindInPageAction findInPage:
                await WriteFindInPageAsync(ux, findInPage);
                break;

            case WebSearchOpenPageAction openPage:
                await WriteOpenPageAsync(ux, openPage);
                break;

            case WebSearchSearchAction search:
                await WriteSearchAsync(ux, search, outputs);
                break;

            default:
                await ux.WriteInfoLineAsync("🌐 Web Search Tool (unknown action)", ConsoleColor.DarkCyan);
                break;
        }
    }

    private static async Task WriteSearchAsync(IUXStateDriver ux, WebSearchSearchAction search, IList<AIContent>? outputs)
    {
        // Read queries directly from the typed action.
        IList<string> queries = search.Queries;

        if (queries.Count == 0)
        {
            await ux.WriteInfoLineAsync("🌐 Web Search Tool: search", ConsoleColor.DarkCyan);
            return;
        }

        var sb = new StringBuilder();
        sb.Append("🌐 Web Search Tool: search");

        // Show the search queries.
        bool hasResults = outputs is { Count: > 0 };
        for (int i = 0; i < queries.Count; i++)
        {
            string connector = (i < queries.Count - 1 || hasResults) ? "├─" : "└─";
            string query = Truncate(queries[i], MaxQueryDisplayLength);
            sb.Append($"\n   {connector} \"{query}\"");
        }

        // Show search result sources (URLs + titles) when available.
        // Sources come from M.E.AI's Outputs when IncludedResponseProperty.WebSearchCallActionSources is set,
        // or directly from the SDK's WebSearchSearchAction.Sources.
        if (hasResults)
        {
            sb.Append("\n   │");
            for (int i = 0; i < outputs!.Count; i++)
            {
                string connector = i < outputs.Count - 1 ? "├─" : "└─";
                string line = FormatOutput(outputs[i]);
                sb.Append($"\n   {connector} {line}");
            }
        }
        else if (search.Sources is { Count: > 0 } sources)
        {
            sb.Append("\n   │");
            for (int i = 0; i < sources.Count; i++)
            {
                string connector = i < sources.Count - 1 ? "├─" : "└─";
                string line = FormatSource(sources[i]);
                sb.Append($"\n   {connector} {line}");
            }
        }

        await ux.WriteInfoLineAsync(sb.ToString(), ConsoleColor.DarkCyan);
    }

    private static async Task WriteOpenPageAsync(IUXStateDriver ux, WebSearchOpenPageAction openPage)
    {
        string url = openPage.Uri?.AbsoluteUri ?? "(unknown)";
        await ux.WriteInfoLineAsync(
            $"🌐 Web Search Tool: open page\n   └─ {url}",
            ConsoleColor.DarkCyan);
    }

    private static async Task WriteFindInPageAsync(IUXStateDriver ux, WebSearchFindInPageAction findInPage)
    {
        string url = findInPage.Uri?.AbsoluteUri ?? "(unknown)";
        string pattern = findInPage.Pattern ?? "(unknown)";

        await ux.WriteInfoLineAsync(
            $"🌐 Web Search Tool: find in page\n   ├─ \"{Truncate(pattern, MaxQueryDisplayLength)}\"\n   └─ {url}",
            ConsoleColor.DarkCyan);
    }

    /// <summary>
    /// Formats a single search result source from the SDK's <see cref="WebSearchActionSource"/> for display.
    /// </summary>
    private static string FormatSource(WebSearchActionSource source)
    {
        if (source is WebSearchActionUriSource uriSource)
        {
            string url = uriSource.Uri?.AbsoluteUri ?? "(unknown)";

            // WebSearchActionUriSource doesn't expose a title property,
            // but the API may include one in the raw response JSON.
            string? title = GetTitleFromRawRepresentation(uriSource);

            return title is not null
                ? $"{Truncate(title, MaxQueryDisplayLength)} — {url}"
                : url;
        }

        return source.ToString() ?? "(unknown source)";
    }

    /// <summary>
    /// Formats a single search result output from M.E.AI's <see cref="AIContent"/> for display.
    /// </summary>
    private static string FormatOutput(AIContent output)
    {
        if (output is UriContent uriContent)
        {
            string url = uriContent.Uri?.AbsoluteUri ?? "(unknown)";

            // Try to extract a title from the raw JSON of the source.
            // The SDK's WebSearchActionUriSource doesn't expose a title property,
            // but the API may include one in the raw response.
            string? title = GetTitleFromRawRepresentation(uriContent.RawRepresentation)
                ?? (uriContent.AdditionalProperties?.TryGetValue("title", out var t) is true ? t?.ToString() : null);

            return title is not null
                ? $"{Truncate(title, MaxQueryDisplayLength)} — {url}"
                : url;
        }

        return output.ToString() ?? "(unknown output)";
    }

    /// <summary>
    /// Attempts to extract a "title" field from a raw representation object by serializing it to JSON.
    /// The SDK's <see cref="WebSearchActionUriSource"/> doesn't expose a title property,
    /// but the API may include one in the raw JSON — this is forward-compatible for when
    /// the SDK adds title support.
    /// </summary>
    private static string? GetTitleFromRawRepresentation(object? rawRepresentation)
    {
        if (rawRepresentation is null)
        {
            return null;
        }

        try
        {
            var data = System.ClientModel.Primitives.ModelReaderWriter.Write(rawRepresentation);
            using var doc = System.Text.Json.JsonDocument.Parse(data);
            if (doc.RootElement.TryGetProperty("title", out var titleEl)
                && titleEl.ValueKind == System.Text.Json.JsonValueKind.String)
            {
                return titleEl.GetString();
            }
        }
        catch
        {
            // Serialization may not be supported for this object type.
        }

        return null;
    }

    private static string Truncate(string text, int maxLength)
        => text.Length <= maxLength ? text : string.Concat(text.AsSpan(0, maxLength - 1), "…");
}
