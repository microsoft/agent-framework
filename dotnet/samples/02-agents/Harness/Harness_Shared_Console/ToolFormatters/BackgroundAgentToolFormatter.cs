// Copyright (c) Microsoft. All rights reserved.

using System.Text;
using Microsoft.Extensions.AI;

namespace Harness.Shared.Console.ToolFormatters;

/// <summary>
/// Formats <c>BackgroundAgents_*</c> tool calls with human-readable details
/// for task start, continue, wait, and result retrieval operations.
/// </summary>
public sealed class BackgroundAgentToolFormatter : ToolCallFormatter
{
    /// <inheritdoc/>
    public override bool CanFormat(FunctionCallContent call) => call.Name.StartsWith("BackgroundAgents_", StringComparison.Ordinal);

    /// <inheritdoc/>
    public override string? FormatDetail(FunctionCallContent call) => call.Name switch
    {
        "BackgroundAgents_StartTask" => FormatStartBackgroundTask(call),
        "BackgroundAgents_WaitForFirstCompletion" => FormatIdList(call, "taskIds", "Wait for"),
        "BackgroundAgents_GetTaskResults" => FormatSingleId(call, "taskId"),
        "BackgroundAgents_ContinueTask" => FormatContinueTask(call),
        "BackgroundAgents_ClearCompletedTask" => FormatSingleId(call, "taskId"),
        _ => null,
    };

    private static string? FormatStartBackgroundTask(FunctionCallContent call)
    {
        string? agentName = GetStringArgumentValue(call, "agentName");
        string? description = GetStringArgumentValue(call, "description");

        if (agentName is null && description is null)
        {
            return null;
        }

        var sb = new StringBuilder();

        if (agentName is not null && description is not null)
        {
            sb.Append($"\n   ├─ Agent: {agentName}");
            sb.Append($"\n   └─ \"{Truncate(description, 80)}\"");
        }
        else if (agentName is not null)
        {
            sb.Append($"\n   └─ Agent: {agentName}");
        }
        else
        {
            sb.Append($"\n   └─ \"{Truncate(description!, 80)}\"");
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

    private static string? FormatSingleId(FunctionCallContent call, string paramName)
    {
        int? id = GetIntArgumentValue(call, paramName);
        return id.HasValue ? $"(task #{id.Value})" : null;
    }

    private static string? FormatContinueTask(FunctionCallContent call)
    {
        int? taskId = GetIntArgumentValue(call, "taskId");
        string? text = GetStringArgumentValue(call, "text");

        if (!taskId.HasValue)
        {
            return null;
        }

        if (text is not null)
        {
            var sb = new StringBuilder();
            sb.Append($"\n   ├─ Task #{taskId.Value}");
            sb.Append($"\n   └─ \"{Truncate(text, 80)}\"");
            return sb.ToString();
        }

        return $"\n   └─ Task #{taskId.Value}";
    }
}
