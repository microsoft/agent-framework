// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Extensions.AI;

namespace Harness.Shared.Console.ToolFormatters;

/// <summary>
/// Formats <c>FileMemory_*</c> tool calls, showing file names and search patterns
/// with tree-view corners for save operations.
/// </summary>
public sealed class FileMemoryToolFormatter : ToolCallFormatter
{
    /// <inheritdoc/>
    public override bool CanFormat(FunctionCallContent call) => call.Name.StartsWith("FileMemory_", StringComparison.Ordinal);

    /// <inheritdoc/>
    public override string? FormatDetail(FunctionCallContent call) => call.Name switch
    {
        "FileMemory_SaveFile" => FormatSaveFile(call),
        "FileMemory_ReadFile" => FormatStringArg(call, "fileName"),
        "FileMemory_DeleteFile" => FormatStringArg(call, "fileName"),
        "FileMemory_SearchFiles" => FormatSearchFiles(call),
        _ => null,
    };

    private static string? FormatSaveFile(FunctionCallContent call)
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

    private static string? FormatSearchFiles(FunctionCallContent call)
    {
        string? pattern = GetStringArgumentValue(call, "regexPattern");
        string? filePattern = GetStringArgumentValue(call, "filePattern");

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
        string? value = GetStringArgumentValue(call, paramName);
        return value is not null ? $"({value})" : null;
    }
}
