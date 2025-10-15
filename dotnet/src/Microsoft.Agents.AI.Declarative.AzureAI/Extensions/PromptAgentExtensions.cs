// Copyright (c) Microsoft. All rights reserved.
using System;
using System.Collections.Generic;
using System.Linq;
using Azure.AI.Agents.Persistent;
using Microsoft.Extensions.AI;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Bot.ObjectModel;

/// <summary>
/// Extension methods for <see cref="PromptAgent"/>.
/// </summary>
internal static class PromptAgentExtensions
{
    /// <summary>
    /// Return the Foundry tool definitions which corresponds with the provided <see cref="PromptAgent"/>.
    /// </summary>
    /// <param name="promptAgent">Instance of <see cref="PromptAgent"/></param>
    /// <param name="tools">Instance of <see cref="IList{AITool}"/></param>
    internal static IEnumerable<Azure.AI.Agents.Persistent.ToolDefinition> GetToolDefinitions(this PromptAgent promptAgent, IList<AITool>? tools)
    {
        Throw.IfNull(promptAgent);

        var optionTools = tools?.Select<AITool, Azure.AI.Agents.Persistent.ToolDefinition>(tool =>
        {
            return tool switch
            {
                HostedCodeInterpreterTool => ((HostedCodeInterpreterTool)tool).CreateHostedCodeInterpreterToolDefinition(),
                AIFunction => ((AIFunction)tool).CreateFunctionToolDefinition(),
                HostedFileSearchTool => ((HostedFileSearchTool)tool).CreateFileSearchToolDefinition(),
                HostedWebSearchTool => ((HostedWebSearchTool)tool).CreateBingGroundingToolDefinition(),
                HostedMcpServerTool => ((HostedMcpServerTool)tool).CreateMcpToolDefinition(),
                _ => throw new NotSupportedException($"Unable to create tool definition because of unsupported tool type: {tool}"),
            };
        }).ToList() ?? [];

        var promptTools = promptAgent.Tools.Select<AgentTool, Azure.AI.Agents.Persistent.ToolDefinition>(tool =>
        {
            return tool switch
            {
                CodeInterpreterTool => ((CodeInterpreterTool)tool).CreateCodeInterpreterToolDefinition(),
                FunctionTool => ((FunctionTool)tool).CreateFunctionToolDefinition(),
                //FileSearchTool => ((FileSearchTool)tool).CreateFileSearchTool(),
                //WebSearchTool => ((WebSearchTool)tool).CreateWebSearchTool(),
                //McpTool => ((McpTool)tool).CreateMcpTool(),
                _ => throw new NotSupportedException($"Unable to create tool definition because of unsupported tool type: {tool.Kind}"),
            };
        }).ToList() ?? [];

        return optionTools != null
            ? [.. promptTools, .. optionTools]
            : promptTools;
        /*
        return promptAgent.Tools.Select<AgentTool, Azure.AI.Agents.Persistent.ToolDefinition>(tool =>
        {
            var type = tool.ExtensionData?.GetString("type");
            return type switch
            {
                CodeInterpreterType => tool.CreateCodeInterpreterToolDefinition(),
                AzureAISearchType => tool.CreateAzureAISearchToolDefinition(),
                AzureFunctionType => tool.CreateAzureFunctionToolDefinition(),
                BingGroundingType => tool.CreateBingGroundingToolDefinition(),
                FileSearchType => tool.CreateFileSearchToolDefinition(),
                FunctionType => tool.CreateFunctionToolDefinition(),
                OpenApiType => tool.CreateOpenApiToolDefinition(),
                McpType => tool.CreateMcpToolDefinition(),
                _ => throw new NotSupportedException($"Unable to create tool definition because of unsupported tool type: {type}, supported tool types are: {string.Join(",", s_validToolTypes)}"),
            };
        }) ?? [];
        */
    }

    /// <summary>
    /// Return the Foundry tool resources which corresponds with the provided <see cref="PromptAgent"/>.
    /// </summary>
    /// <param name="promptAgent">Instance of <see cref="PromptAgent"/></param>
    internal static ToolResources GetToolResources(this PromptAgent promptAgent)
    {
        Throw.IfNull(promptAgent);

        /*
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
        var azureAISearch = promptAgent.GetAzureAISearchResource();
        if (azureAISearch is not null)
        {
            toolResources.AzureAISearch = azureAISearch;
        }
        */

        return new ToolResources();
    }

    /*
    /// <summary>
    /// Return the temperature which corresponds with the provided <see cref="PromptAgent"/>.
    /// </summary>
    /// <param name="promptAgent">Instance of <see cref="PromptAgent"/></param>
    internal static float? GetTemperature(this PromptAgent promptAgent)
    {
        Throw.IfNull(promptAgent);

        var temperature = promptAgent.ExtensionData?.GetPropertyOrNull<NumberDataValue>(InitializablePropertyPath.Create("model.options.temperature"));
        return (float?)temperature?.Value;
    }

    /// <summary>
    /// Return the top_p which corresponds with the provided <see cref="PromptAgent"/>.
    /// </summary>
    /// <param name="promptAgent">Instance of <see cref="PromptAgent"/></param>
    internal static float? GetTopP(this PromptAgent promptAgent)
    {
        Throw.IfNull(promptAgent);

        var topP = promptAgent.ExtensionData?.GetPropertyOrNull<NumberDataValue>(InitializablePropertyPath.Create("model.options.top_p"));
        return (float?)topP?.Value;
    }

    /// <summary>
    /// Return the response_format which corresponds with the provided <see cref="PromptAgent"/>.
    /// </summary>
    /// <param name="promptAgent">Instance of <see cref="PromptAgent"/></param>
    internal static BinaryData? GetResponseFormat(this PromptAgent promptAgent)
    {
        Throw.IfNull(promptAgent);

        try
        {
            var responseFormatStr = promptAgent.ExtensionData?.GetPropertyOrNull<StringDataValue>(InitializablePropertyPath.Create("model.options.response_format"));
            if (responseFormatStr?.Value is not null)
            {
                return new BinaryData(responseFormatStr.Value);
            }
        }
        catch (InvalidCastException)
        {
            // Ignore and try next
        }

        var responseFormRec = promptAgent.ExtensionData?.GetPropertyOrNull<RecordDataValue>(InitializablePropertyPath.Create("model.options.response_format"));
        if (responseFormRec is not null)
        {
#pragma warning disable IL2026 // Members annotated with 'RequiresUnreferencedCodeAttribute' require dynamic access otherwise can break functionality when trimming application code
#pragma warning disable IL3050 // Calling members annotated with 'RequiresDynamicCodeAttribute' may break functionality when AOT compiling.
            var json = JsonSerializer.Serialize(responseFormRec, ElementSerializer.CreateOptions());
#pragma warning restore IL3050 // Calling members annotated with 'RequiresDynamicCodeAttribute' may break functionality when AOT compiling.
#pragma warning restore IL2026 // Members annotated with 'RequiresUnreferencedCodeAttribute' require dynamic access otherwise can break functionality when trimming application code
            return new BinaryData(json);
        }

        return null;
    }

    #region private
    private const string AzureAISearchType = "azure_ai_search";
    private const string AzureFunctionType = "azure_function";
    private const string BingGroundingType = "bing_grounding";
    private const string CodeInterpreterType = "code_interpreter";
    private const string FileSearchType = "file_search";
    private const string FunctionType = "function";
    private const string OpenApiType = "openapi";
    private const string McpType = "mcp";

    private static readonly string[] s_validToolTypes =
    [
        AzureAISearchType,
        AzureFunctionType,
        BingGroundingType,
        CodeInterpreterType,
        FileSearchType,
        FunctionType,
        OpenApiType,
        McpType
    ];

    private static CodeInterpreterToolResource? GetCodeInterpreterToolResource(this PromptAgent promptAgent)
    {
        Throw.IfNull(promptAgent);

        CodeInterpreterToolResource? resource = null;

        var codeInterpreter = promptAgent.GetFirstToolDefinition(CodeInterpreterType);
        if (codeInterpreter is not null)
        {
            var fileIds = codeInterpreter.GetFileIds();
            var dataSources = codeInterpreter.ExtensionData?.GetDataSources();
            if (fileIds is not null || dataSources is not null)
            {
                resource = new CodeInterpreterToolResource();
                fileIds?.ForEach(id => resource.FileIds.Add(id));
                dataSources?.ForEach(ds => resource.DataSources.Add(ds));
            }
        }

        return resource;
    }

    private static FileSearchToolResource? GetFileSearchToolResource(this PromptAgent promptAgent)
    {
        Throw.IfNull(promptAgent);

        var fileSearch = promptAgent.GetFirstToolDefinition(FileSearchType);
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

    private static AzureAISearchToolResource? GetAzureAISearchResource(this PromptAgent promptAgent)
    {
        Throw.IfNull(promptAgent);

        var azureAISearch = promptAgent.GetFirstToolDefinition(AzureAISearchType);
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

    private static AgentTool? GetFirstToolDefinition(this PromptAgent promptAgent, string toolType)
    {
        return promptAgent.Tools.FirstOrDefault(tool => tool.ExtensionData?.GetString("type") == toolType);
    }
    #endregion
    */
}
