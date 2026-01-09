// Copyright (c) Microsoft. All rights reserved.
using System;
using System.Collections.Generic;
using System.Linq;
using Azure.AI.Agents.Persistent;
using Microsoft.Shared.Diagnostics;
using OpenAI.Responses;

namespace Microsoft.Bot.ObjectModel;

/// <summary>
/// Extension methods for <see cref="GptComponentMetadata"/>.
/// </summary>
internal static class PromptAgentExtensions
{
    /// <summary>
    /// Return the Foundry tool definitions which corresponds with the provided <see cref="GptComponentMetadata"/>.
    /// </summary>
    /// <param name="promptAgent">Instance of <see cref="GptComponentMetadata"/></param>
    internal static IEnumerable<Azure.AI.Agents.Persistent.ToolDefinition> GetToolDefinitions(this GptComponentMetadata promptAgent)
    {
        Throw.IfNull(promptAgent);

        return promptAgent.Tools.Select<TaskAction, Azure.AI.Agents.Persistent.ToolDefinition>(tool =>
        {
            return tool switch
            {
                CodeInterpreterTool codeInterpreterTool => codeInterpreterTool.CreateCodeInterpreterToolDefinition(),
                InvokeClientTaskAction functionTool => functionTool.CreateFunctionToolDefinition(),
                FileSearchTool fileSearchTool => fileSearchTool.CreateFileSearchToolDefinition(),
                WebSearchTool webSearchTool => webSearchTool.CreateBingGroundingToolDefinition(),
                McpServerTool mcpServerTool => mcpServerTool.CreateMcpToolDefinition(),
                // TODO: Add other tool types as custom tools
                // AzureAISearch
                // AzureFunction
                // OpenApi
                _ => throw new NotSupportedException($"Unable to create tool definition because of unsupported tool type: {tool.Kind}"),
            };
        }).ToList();
    }

    /// <summary>
    /// Return the Foundry tool resources which corresponds with the provided <see cref="GptComponentMetadata"/>.
    /// </summary>
    /// <param name="promptAgent">Instance of <see cref="GptComponentMetadata"/></param>
    internal static ToolResources GetToolResources(this GptComponentMetadata promptAgent)
    {
        Throw.IfNull(promptAgent);

        var toolResources = new ToolResources();

        var codeInterpreter = promptAgent.GetCodeInterpreterToolResource();
        if (codeInterpreter is not null)
        {
            toolResources.CodeInterpreter = codeInterpreter;
        }

        var fileSearch = promptAgent.GetFileSearchToolResource();
        if (fileSearch is not null)
        {
            toolResources.FileSearch = fileSearch;
        }

        // TODO Handle MCP tool resources

        return toolResources;
    }

    /// <summary>
    /// Returns the Foundry response tools which correspond with the provided <see cref="GptComponentMetadata"/>.
    /// </summary>
    /// <param name="promptAgent">Instance of <see cref="GptComponentMetadata"/>.</param>
    /// <returns>A collection of <see cref="ResponseTool"/> instances corresponding to the tools defined in the agent.</returns>
    internal static IEnumerable<ResponseTool> GetResponseTools(this GptComponentMetadata promptAgent)
    {
        Throw.IfNull(promptAgent);

        return promptAgent.Tools.Select<TaskAction, ResponseTool>(tool =>
        {
            return tool switch
            {
                CodeInterpreterTool codeInterpreterTool => codeInterpreterTool.CreateCodeInterpreterTool(),
                InvokeClientTaskAction functionTool => functionTool.CreateFunctionTool(),
                FileSearchTool fileSearchTool => fileSearchTool.CreateFileSearchTool(),
                WebSearchTool webSearchTool => webSearchTool.CreateWebSearchTool(),
                McpServerTool mcpServerTool => mcpServerTool.CreateMcpTool(),
                // TODO: Add other tool types as custom tools
                // AzureAISearch
                // AzureFunction
                // OpenApi
                _ => throw new NotSupportedException($"Unable to create response tool because of unsupported tool type: {tool.Kind}"),
            };
        }).ToList();
    }

    #region private
    private static CodeInterpreterToolResource? GetCodeInterpreterToolResource(this GptComponentMetadata promptAgent)
    {
        Throw.IfNull(promptAgent);

        CodeInterpreterToolResource? resource = null;

        var codeInterpreter = (CodeInterpreterTool?)promptAgent.GetFirstAgentTool<CodeInterpreterTool>();
        if (codeInterpreter is not null)
        {
            var fileIds = codeInterpreter.GetFileIds();
            var dataSources = codeInterpreter.GetDataSources();
            if (fileIds is not null || dataSources is not null)
            {
                resource = new CodeInterpreterToolResource();
                fileIds?.ForEach(id => resource.FileIds.Add(id));
                dataSources?.ForEach(ds => resource.DataSources.Add(ds));
            }
        }

        return resource;
    }

    private static FileSearchToolResource? GetFileSearchToolResource(this GptComponentMetadata promptAgent)
    {
        Throw.IfNull(promptAgent);

        var fileSearch = (FileSearchTool?)promptAgent.GetFirstAgentTool<FileSearchTool>();
        if (fileSearch is not null)
        {
            var vectorStoreIds = fileSearch.GetVectorStoreIds();
            var vectorStores = fileSearch.GetVectorStoreConfigurations();
            if (vectorStoreIds is not null || vectorStores is not null)
            {
                return new FileSearchToolResource(vectorStoreIds, vectorStores);
            }
        }

        return null;
    }

    private static TaskAction? GetFirstAgentTool<T>(this GptComponentMetadata promptAgent)
    {
        return promptAgent.Tools.FirstOrDefault(tool => tool is T);
    }
    #endregion
}
