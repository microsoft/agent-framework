// Copyright (c) Microsoft. All rights reserved.

using System.Text;
using System.Text.Json;
using Microsoft.Extensions.AI;

namespace Harness.Shared.Console.Observers;

/// <summary>
/// Formats <see cref="FunctionCallContent"/> instances into human-readable strings
/// for console display.
/// </summary>
public static class ToolCallFormatter
{
    /// <summary>
    /// Returns a formatted string for the given tool call, with human-readable
    /// details for known tools (todos, mode, sub-agents, web tools).
    /// </summary>
    /// <param name="call">The function call content to format.</param>
    /// <returns>A formatted string describing the tool call.</returns>
    public static string Format(FunctionCallContent call)
    {
        string? detail = call.Name switch
        {
            // Todo tools
            "TodoList_Add" => FormatAddTodos(call),
            "TodoList_Complete" => FormatIdList(call, "ids", "Complete"),
            "TodoList_Remove" => FormatIdList(call, "ids", "Remove"),
            "TodoList_GetRemaining" => null,
            "TodoList_GetAll" => null,

            // Mode tools
            "AgentMode_Set" => FormatStringArg(call, "mode"),
            "AgentMode_Get" => null,

            // Sub-agent tools
            "SubAgents_StartTask" => FormatStartSubTask(call),
            "SubAgents_WaitForFirstCompletion" => FormatIdList(call, "taskIds", "Wait for"),
            "SubAgents_GetTaskResults" => FormatSingleId(call, "taskId"),
            "SubAgents_GetAllTasks" => null,
            "SubAgents_ContinueTask" => FormatContinueTask(call),
            "SubAgents_ClearCompletedTask" => FormatSingleId(call, "taskId"),

            // File memory tools
            "FileMemory_SaveFile" => FormatSaveFile(call),
            "FileMemory_ReadFile" => FormatStringArg(call, "fileName"),
            "FileMemory_DeleteFile" => FormatStringArg(call, "fileName"),
            "FileMemory_ListFiles" => null,
            "FileMemory_SearchFiles" => FormatSearchFiles(call),

            // External tools
            "web_search" => FormatStringArg(call, "query"),
            "DownloadUri" => FormatStringArg(call, "uri"),

            _ => FormatFallback(call),
        };

        return detail is not null ? $"{call.Name} {detail}" : call.Name;
    }

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
        foreach (string title in titles)
        {
            sb.Append($"\n    • {title}");
        }

        return sb.ToString();
    }

    private static string? FormatIdList(FunctionCallContent call, string paramName, string verb)
    {
        List<int>? ids = GetIntList(call, paramName);
        if (ids is null || ids.Count == 0)
        {
            return null;
        }

        return $"({verb} #{string.Join(", #", ids)})";
    }

    private static string? FormatSingleId(FunctionCallContent call, string paramName)
    {
        int? id = GetInt(call, paramName);
        return id.HasValue ? $"(task #{id.Value})" : null;
    }

    private static string? FormatStartSubTask(FunctionCallContent call)
    {
        string? agentName = GetString(call, "agentName");
        string? description = GetString(call, "description");

        if (agentName is null && description is null)
        {
            return null;
        }

        var sb = new StringBuilder("(");
        if (agentName is not null)
        {
            sb.Append($"agent: {agentName}");
        }

        if (description is not null)
        {
            if (agentName is not null)
            {
                sb.Append(", ");
            }

            sb.Append($"\"{Truncate(description, 60)}\"");
        }

        sb.Append(')');
        return sb.ToString();
    }

    private static string? FormatContinueTask(FunctionCallContent call)
    {
        int? taskId = GetInt(call, "taskId");
        string? text = GetString(call, "text");

        if (!taskId.HasValue)
        {
            return null;
        }

        return text is not null
            ? $"(task #{taskId.Value}, \"{Truncate(text, 50)}\")"
            : $"(task #{taskId.Value})";
    }

    private static string? FormatSaveFile(FunctionCallContent call)
    {
        string? fileName = GetString(call, "fileName");
        string? description = GetString(call, "description");

        if (fileName is null)
        {
            return null;
        }

        return string.IsNullOrEmpty(description)
            ? $"({fileName})"
            : $"({fileName}, with description)";
    }

    private static string? FormatSearchFiles(FunctionCallContent call)
    {
        string? pattern = GetString(call, "regexPattern");
        string? filePattern = GetString(call, "filePattern");

        if (pattern is null)
        {
            return null;
        }

        return string.IsNullOrEmpty(filePattern)
            ? $"(/{pattern}/)"
            : $"(/{pattern}/ in {filePattern})";
    }

    private static string? FormatStringArg(FunctionCallContent call, string paramName)
    {
        string? value = GetString(call, paramName);
        return value is not null ? $"({value})" : null;
    }

    private static string? FormatFallback(FunctionCallContent call)
    {
        if (call.Arguments is null || call.Arguments.Count == 0)
        {
            return null;
        }

        var parts = new List<string>();
        foreach (var kvp in call.Arguments)
        {
            string? stringValue = kvp.Value switch
            {
                JsonElement je => je.ValueKind switch
                {
                    JsonValueKind.String => je.GetString(),
                    JsonValueKind.Number => je.GetRawText(),
                    JsonValueKind.True => "true",
                    JsonValueKind.False => "false",
                    _ => null,
                },
                not null => kvp.Value.ToString(),
                _ => null,
            };

            if (stringValue is not null)
            {
                parts.Add($"{kvp.Key}: {Truncate(stringValue, 40)}");
            }
        }

        return parts.Count > 0 ? $"({string.Join(", ", parts)})" : null;
    }

    private static string? GetString(FunctionCallContent call, string paramName)
    {
        if (call.Arguments?.TryGetValue(paramName, out object? value) != true || value is null)
        {
            return null;
        }

        return value switch
        {
            JsonElement je when je.ValueKind == JsonValueKind.String => je.GetString(),
            string s => s,
            _ => value.ToString(),
        };
    }

    private static int? GetInt(FunctionCallContent call, string paramName)
    {
        if (call.Arguments?.TryGetValue(paramName, out object? value) != true || value is null)
        {
            return null;
        }

        return value switch
        {
            JsonElement je when je.ValueKind == JsonValueKind.Number => je.GetInt32(),
            int i => i,
            _ => int.TryParse(value.ToString(), out int parsed) ? parsed : null,
        };
    }

    private static List<int>? GetIntList(FunctionCallContent call, string paramName)
    {
        if (call.Arguments?.TryGetValue(paramName, out object? value) != true || value is null)
        {
            return null;
        }

        var result = new List<int>();

        if (value is JsonElement je && je.ValueKind == JsonValueKind.Array)
        {
            foreach (JsonElement item in je.EnumerateArray())
            {
                if (item.ValueKind == JsonValueKind.Number)
                {
                    result.Add(item.GetInt32());
                }
            }
        }

        return result.Count > 0 ? result : null;
    }

    private static string Truncate(string text, int maxLength)
    {
        return text.Length <= maxLength ? text : string.Concat(text.AsSpan(0, maxLength), "…");
    }
}
