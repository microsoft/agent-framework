// Copyright (c) Microsoft. All rights reserved.

using System.Text;
using System.Text.Json;
using Microsoft.Extensions.AI;

namespace Harness.Shared.Console.ToolFormatters;

/// <summary>
/// Formats <c>todos_*</c> tool calls with tree-view output for added items
/// and structured output for complete/remove operations.
/// </summary>
public sealed class TodoToolFormatter : ToolCallFormatter
{
    /// <inheritdoc/>
    public override bool CanFormat(FunctionCallContent call) => call.Name.StartsWith("todos_", StringComparison.Ordinal);

    /// <inheritdoc/>
    public override string? FormatDetail(FunctionCallContent call) => call.Name switch
    {
        "todos_add" => FormatAddTodos(call),
        "todos_complete" => FormatCompleteTodos(call),
        "todos_remove" => FormatIdList(call, "ids", "Remove"),
        _ => null,
    };

    private static string? FormatAddTodos(FunctionCallContent call)
    {
        if (call.Arguments?.TryGetValue("todos", out object? todosObj) != true || todosObj is null)
        {
            return null;
        }

        var titles = new List<string>();

        if (todosObj is JsonElement jsonArray && jsonArray.ValueKind == JsonValueKind.Array)
        {
            foreach (JsonElement item in jsonArray.EnumerateArray())
            {
                string? title = item.TryGetProperty("title", out JsonElement titleElement)
                    ? titleElement.GetString()
                    : null;

                if (!string.IsNullOrEmpty(title))
                {
                    titles.Add(title);
                }
            }
        }

        if (titles.Count == 0)
        {
            return null;
        }

        var sb = new StringBuilder();
        sb.Append($"({titles.Count} item{(titles.Count == 1 ? "" : "s")})");
        for (int i = 0; i < titles.Count; i++)
        {
            string connector = i < titles.Count - 1 ? "├─" : "└─";
            sb.Append($"\n   {connector} {titles[i]}");
        }

        return sb.ToString();
    }

    private static string? FormatCompleteTodos(FunctionCallContent call)
    {
        if (call.Arguments?.TryGetValue("items", out object? itemsObj) != true || itemsObj is null)
        {
            return null;
        }

        var entries = new List<(int Id, string? Reason)>();

        if (itemsObj is JsonElement jsonArray && jsonArray.ValueKind == JsonValueKind.Array)
        {
            foreach (JsonElement item in jsonArray.EnumerateArray())
            {
                if (!item.TryGetProperty("id", out JsonElement idElement) || !idElement.TryGetInt32(out int id))
                {
                    continue;
                }

                string? reason = item.TryGetProperty("reason", out JsonElement reasonElement)
                    ? reasonElement.GetString()
                    : null;
                entries.Add((id, reason));
            }
        }

        if (entries.Count == 0)
        {
            return null;
        }

        var sb = new StringBuilder();
        for (int i = 0; i < entries.Count; i++)
        {
            string connector = i < entries.Count - 1 ? "├─" : "└─";
            sb.Append($"\n   {connector} Complete #{entries[i].Id}");
            if (!string.IsNullOrEmpty(entries[i].Reason))
            {
                sb.Append($" — {Truncate(entries[i].Reason!, 80)}");
            }
        }

        return sb.ToString();
    }

    private static string? FormatIdList(FunctionCallContent call, string paramName, string verb)
    {
        List<int>? ids = GetIntListArgumentValue(call, paramName);
        if (ids is null || ids.Count == 0)
        {
            return null;
        }

        var sb = new StringBuilder();
        for (int i = 0; i < ids.Count; i++)
        {
            string connector = i < ids.Count - 1 ? "├─" : "└─";
            sb.Append($"\n   {connector} {verb} #{ids[i]}");
        }

        return sb.ToString();
    }
}
