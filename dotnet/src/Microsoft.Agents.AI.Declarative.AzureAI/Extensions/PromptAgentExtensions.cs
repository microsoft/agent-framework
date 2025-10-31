// Copyright (c) Microsoft. All rights reserved.
using System;
using System.Collections.Generic;
using System.Linq;
using Azure.AI.Agents.Persistent;
using Microsoft.Shared.Diagnostics;

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
                CodeInterpreterTool => ((CodeInterpreterTool)tool).CreateCodeInterpreterToolDefinition(),
                InvokeClientTaskAction => ((InvokeClientTaskAction)tool).CreateFunctionToolDefinition(),
                FileSearchTool => ((FileSearchTool)tool).CreateFileSearchToolDefinition(),
                WebSearchTool => ((WebSearchTool)tool).CreateBingGroundingToolDefinition(),
                McpServerTool => ((McpServerTool)tool).CreateMcpToolDefinition(),
                // TODO: Add other tool types when implemented
                // AzureAISearch
                // AzureFunction
                // OpenApi
                _ => throw new NotSupportedException($"Unable to create tool definition because of unsupported tool type: {tool.Kind}"),
            };
        }).ToList() ?? [];
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
        //var azureAISearch = promptAgent.GetAzureAISearchResource();
        //if (azureAISearch is not null)
        //{
        //    toolResources.AzureAISearch = azureAISearch;
        //}

        return new ToolResources();
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

    /*
    private static AzureAISearchToolResource? GetAzureAISearchResource(this PromptAgent promptAgent)
    {
        Throw.IfNull(promptAgent);

        var azureAISearch = promptAgent.GetFirstAgentTool<SearchTool>();
        if (azureAISearch is not null)
        {
            string? indexConnectionId = azureAISearch.ExtensionData?.GetPropertyOrNull<StringDataValue>(InitializablePropertyPath.Create("options.index_connection_id"))?.Value;
            string? indexName = azureAISearch.ExtensionData?.GetPropertyOrNull<StringDataValue>(InitializablePropertyPath.Create("options.index_name"))?.Value;
            if (string.IsNullOrEmpty(indexConnectionId) && string.IsNullOrEmpty(indexName))
            {
                return null;
            }
            if (string.IsNullOrEmpty(indexConnectionId) || string.IsNullOrEmpty(indexName))
            {
                throw new InvalidOperationException("Azure AI Search tool definition must have both 'index_connection_id' and 'index_name' options set.");
            }
            int topK = azureAISearch.GetTopK() ?? 5;
            string filter = azureAISearch.GetFilter() ?? string.Empty;
            AzureAISearchQueryType? queryType = azureAISearch.GetAzureAISearchQueryType();

            return new AzureAISearchToolResource(indexConnectionId, indexName, topK, filter, queryType);
        }

        return null;
    }
    */

    private static TaskAction? GetFirstAgentTool<T>(this GptComponentMetadata promptAgent)
    {
        return promptAgent.Tools.FirstOrDefault(tool => tool is T);
    }
    #endregion
}
