// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json;
using Microsoft.Extensions.AI;

namespace Harness.Shared.Console.ToolFormatters;

/// <summary>
/// Formats <c>file_memory_*</c> tool calls, showing file names and search patterns
/// with tree-view corners for write and edit operations.
/// </summary>
public sealed class FileMemoryToolFormatter : ToolCallFormatter
{
    /// <inheritdoc/>
    public override bool CanFormat(FunctionCallContent call) => call.Name.StartsWith("file_memory_", StringComparison.Ordinal);

    /// <inheritdoc/>
    public override string? FormatDetail(FunctionCallContent call) => call.Name switch
    {
        "file_memory_write" => FormatWriteFile(call),
        "file_memory_read" => FormatStringArg(call, "fileName"),
        "file_memory_delete" => FormatStringArg(call, "fileName"),
        "file_memory_replace" => FormatReplaceFile(call),
        "file_memory_replace_lines" => FormatReplaceLinesFile(call),
        "file_memory_grep" => FormatGrep(call),
        _ => null,
    };

    private static string? FormatWriteFile(FunctionCallContent call)
    {
        string? fileName = GetStringArgumentValue(call, "fileName");
        string? description = GetStringArgumentValue(call, "description");

        if (fileName is null)
        {
            return null;
        }

        return string.IsNullOrEmpty(description)
            ? $"\n   └─ {fileName}"
            : $"\n   └─ {fileName} (with description)";
    }

    private static string? FormatReplaceFile(FunctionCallContent call)
    {
        string? fileName = GetStringArgumentValue(call, "fileName");

        if (fileName is null)
        {
            return null;
        }

        bool replaceAll = string.Equals(GetStringArgumentValue(call, "replaceAll"), "true", StringComparison.OrdinalIgnoreCase);

        return replaceAll
            ? $"\n   └─ {fileName} (replace all)"
            : $"\n   └─ {fileName} (replace)";
    }

    private static string? FormatReplaceLinesFile(FunctionCallContent call)
    {
        string? fileName = GetStringArgumentValue(call, "fileName");

        if (fileName is null)
        {
            return null;
        }

        int count = GetEditsCount(call, "edits");

        return $"\n   └─ {fileName} ({count} line(s))";
    }

    private static int GetEditsCount(FunctionCallContent call, string paramName)
    {
        if (call.Arguments?.TryGetValue(paramName, out object? value) == true &&
            value is JsonElement je && je.ValueKind == JsonValueKind.Array)
        {
            return je.GetArrayLength();
        }

        return 0;
    }

    private static string? FormatGrep(FunctionCallContent call)
    {
        string? pattern = GetStringArgumentValue(call, "regexPattern");
        string? globPattern = GetStringArgumentValue(call, "globPattern");

        if (pattern is null)
        {
            return null;
        }

        return string.IsNullOrEmpty(globPattern)
            ? $"(/{pattern}/)"
            : $"(/{pattern}/ in {globPattern})";
    }

    private static string? FormatStringArg(FunctionCallContent call, string paramName)
    {
        string? value = GetStringArgumentValue(call, paramName);
        return value is not null ? $"({value})" : null;
    }
}
