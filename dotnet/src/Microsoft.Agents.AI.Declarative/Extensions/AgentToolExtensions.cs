// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using Microsoft.Extensions.AI;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Bot.ObjectModel;

/// <summary>
/// Extension methods for <see cref="AgentTool"/>.
/// </summary>
public static class AgentToolExtensions
{
    /// <summary>
    /// Retrieves the 'code_interpreter' tool from a <see cref="AgentTool"/>.
    /// </summary>
    /// <param name="tool">Instance of <see cref="AgentTool"/></param>
    internal static HostedCodeInterpreterTool CreateCodeInterpreterTool(this AgentTool tool)
    {
        Throw.IfNull(tool);

        return new HostedCodeInterpreterTool();
    }

    /// <summary>
    /// Retrieves the 'function' tool from a <see cref="AgentTool"/>.
    /// </summary>
    /// <param name="tool">Instance of <see cref="AgentTool"/></param>
    internal static AIFunctionDeclaration CreateFunctionDeclaration(this AgentTool tool)
    {
        Throw.IfNull(tool);

        string? name = tool.ExtensionData?.GetString("name");
        Throw.IfNull(name);
        string? description = tool.ExtensionData?.GetString("description");
        var jsonSchema = tool.ExtensionData?.GetSchema() ?? new(); // TODO: Validate that this is a valid JSON schema

        return AIFunctionFactory.CreateDeclaration(
            name: name,
            description: description,
            jsonSchema: jsonSchema);
    }

    /// <summary>
    /// Retrieves the 'code-interpreter' tool from a <see cref="AgentTool"/>.
    /// </summary>
    /// <param name="tool">Instance of <see cref="AgentTool"/></param>
    internal static HostedFileSearchTool CreateFileSearchTool(this AgentTool tool)
    {
        Throw.IfNull(tool);

        return new HostedFileSearchTool()
        {
            Inputs = tool.GetHostedVectorStoreContents(),
        };
    }

    /// <summary>
    /// Retrieves the 'code-interpreter' tool from a <see cref="AgentTool"/>.
    /// </summary>
    /// <param name="tool">Instance of <see cref="AgentTool"/></param>
    internal static HostedWebSearchTool CreateWebSearchTool(this AgentTool tool)
    {
        Throw.IfNull(tool);

        return new HostedWebSearchTool();
    }

    /// <summary>
    /// Retrieves the 'code-interpreter' tool from a <see cref="AgentTool"/>.
    /// </summary>
    /// <param name="tool">Instance of <see cref="AgentTool"/></param>
    internal static HostedMcpServerTool CreateMcpTool(this AgentTool tool)
    {
        Throw.IfNull(tool);

        string? serverName = tool.ExtensionData?.GetString("server_name");
        Throw.IfNull(serverName);
        string? serverUrl = tool.ExtensionData?.GetString("server_url");
        Throw.IfNull(serverUrl);

        var serverDescription = tool.ExtensionData?.GetString("server_description");
        var allowedTools = tool.ExtensionData?.GetPropertyOrNull<TableDataValue>(InitializablePropertyPath.Create("allowed_tools"))?.Values
            .Select(t => t.GetPropertyOrNull<StringDataValue>(InitializablePropertyPath.Create("Value"))?.Value!)
            .Where(t => !string.IsNullOrWhiteSpace(t))
            .ToList();

        return new HostedMcpServerTool(serverName, serverUrl)
        {
            ServerDescription = serverDescription,
            AllowedTools = allowedTools,
            ApprovalMode = tool.GetHostedMcpServerToolApprovalMode(),
            Headers = tool.GetHeaders(),
        };
    }

    /// <summary>
    /// Retrieves the 'vector_store_ids' property from a <see cref="AgentTool"/>.
    /// </summary>
    /// <param name="tool">Instance of <see cref="AgentTool"/></param>
    internal static IList<AIContent> GetHostedVectorStoreContents(this AgentTool tool)
    {
        Throw.IfNull(tool);

        var vectorStoreIds = tool.ExtensionData?.GetPropertyOrNull<TableDataValue>(InitializablePropertyPath.Create("vector_store_ids"))?.Values;
        if (vectorStoreIds is null)
        {
            return Array.Empty<HostedVectorStoreContent>();
        }

        return ((IEnumerable<RecordDataValue>)vectorStoreIds)
            .Select(vsi => vsi.GetString("Value"))
            .Where(vsi => !string.IsNullOrWhiteSpace(vsi))
            .Select(vsi => (AIContent)new HostedVectorStoreContent(vsi!))
            .ToList();
    }

    /// <summary>
    /// Retrieves the 'require_approval' property from a <see cref="AgentTool"/>.
    /// </summary>
    /// <param name="tool">Instance of <see cref="AgentTool"/></param>
    internal static HostedMcpServerToolApprovalMode GetHostedMcpServerToolApprovalMode(this AgentTool tool)
    {
        Throw.IfNull(tool);

        var requireApproval = tool.ExtensionData?.GetString("require_approval");
        return requireApproval?.ToUpperInvariant() switch
        {
            "ALWAYS" => HostedMcpServerToolApprovalMode.AlwaysRequire,
            "NEVER" => tool.GetHostedMcpServerToolRequireSpecificApprovalMode(),
            _ => throw new ArgumentOutOfRangeException(nameof(tool), $"Unknown value for require_approval: {requireApproval}"),
        };
    }

    /// <summary>
    /// Retrieves the 'allowed_tools' property from a <see cref="AgentTool"/>.
    /// </summary>
    /// <param name="tool">Instance of <see cref="AgentTool"/></param>
    internal static HostedMcpServerToolApprovalMode GetHostedMcpServerToolRequireSpecificApprovalMode(this AgentTool tool)
    {
        Throw.IfNull(tool);

        var allowedTools = tool.ExtensionData?.GetPropertyOrNull<TableDataValue>(InitializablePropertyPath.Create("allowed_tools"))?.Values;
        if (allowedTools is null)
        {
            return HostedMcpServerToolApprovalMode.NeverRequire;
        }

        var tools = ((IEnumerable<RecordDataValue>)allowedTools)
            .Select(vsi => vsi.GetString("Value"))
            .Where(vsi => !string.IsNullOrWhiteSpace(vsi))
            .Select(vsi => vsi!)
            .ToList();

        return HostedMcpServerToolApprovalMode.RequireSpecific(null, tools);
    }

    /// <summary>
    /// Retrieves the 'headers' property from a <see cref="AgentTool"/>.
    /// </summary>
    /// <param name="tool">Instance of <see cref="AgentTool"/></param>
    internal static IDictionary<string, string>? GetHeaders(this AgentTool tool)
    {
        Throw.IfNull(tool);

        var headers = tool.ExtensionData?.GetPropertyOrNull<RecordDataValue>(InitializablePropertyPath.Create("headers"));
        if (headers is null)
        {
            return null;
        }

        return headers.Properties.ToDictionary(
            kvp => kvp.Key,
            kvp => kvp.Value?.ToString() ?? string.Empty
        );
    }
}
