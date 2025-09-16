// Copyright (c) Microsoft. All rights reserved.

using Azure.AI.Agents.Persistent;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Bot.ObjectModel;

/// <summary>
/// Extension methods for <see cref="GptComponentMetadata"/>.
/// </summary>
/// <remarks>
/// These are temporary helper methods for use while the single agent definition is being added to Microsoft.Bot.ObjectModel.
/// </remarks>
internal static class GptComponentMetadataExtensions
{
    /// <summary>
    /// Return the Foundry tool definitions which corresponds with the provided <see cref="GptComponentMetadata"/>.
    /// </summary>
    /// <param name="element">Instance of <see cref="GptComponentMetadata"/></param>
    public static IEnumerable<Azure.AI.Agents.Persistent.ToolDefinition> GetFoundryToolDefinitions(this GptComponentMetadata element)
    {
        //Throw.IfNull(element);

        return element.GetTools().Select<RecordDataValue, Azure.AI.Agents.Persistent.ToolDefinition>(tool =>
        {
            var type = tool.GetTypeValue();
            return type switch
            {
                AzureAISearchType => tool.CreateAzureAISearchToolDefinition(),
                AzureFunctionType => tool.CreateAzureFunctionToolDefinition(),
                BingGroundingType => tool.CreateBingGroundingToolDefinition(),
                CodeInterpreterType => tool.CreateCodeInterpreterToolDefinition(),
                FileSearchType => tool.CreateFileSearchToolDefinition(),
                FunctionType => tool.CreateFunctionToolDefinition(),
                OpenApiType => tool.CreateOpenApiToolDefinition(),
                _ => throw new NotSupportedException($"Unable to create tool definition because of unsupported tool type: {type}, supported tool types are: {string.Join(",", s_validToolTypes)}"),
            };
        }) ?? [];
    }

    /// <summary>
    /// Return the Foundry tool resources which corresponds with the provided <see cref="GptComponentMetadata"/>.
    /// </summary>
    /// <param name="element">Instance of <see cref="GptComponentMetadata"/></param>
    public static ToolResources GetFoundryToolResources(this GptComponentMetadata element)
    {
        //Throw.IfNull(element);

        var toolResources = new ToolResources();

        var codeInterpreter = element.GetCodeInterpreterToolResource();
        if (codeInterpreter is not null)
        {
            toolResources.CodeInterpreter = codeInterpreter;
        }
        var fileSearch = element.GetFileSearchToolResource();
        if (fileSearch is not null)
        {
            toolResources.FileSearch = fileSearch;
        }
        var azureAISearch = element.GetAzureAISearchResource();
        if (azureAISearch is not null)
        {
            toolResources.AzureAISearch = azureAISearch;
        }

        return toolResources;
    }

    #region private
    private const string AzureAISearchType = "azure_ai_search";
    private const string AzureFunctionType = "azure_function";
    private const string BingGroundingType = "bing_grounding";
    private const string CodeInterpreterType = "code_interpreter";
    private const string FileSearchType = "file_search";
    private const string FunctionType = "function";
    private const string OpenApiType = "openapi";

    private static readonly string[] s_validToolTypes =
    [
        AzureAISearchType,
        AzureFunctionType,
        BingGroundingType,
        CodeInterpreterType,
        FileSearchType,
        FunctionType,
        OpenApiType,
    ];

    private static CodeInterpreterToolResource? GetCodeInterpreterToolResource(this GptComponentMetadata element)
    {
        Throw.IfNull(element);

        CodeInterpreterToolResource? resource = null;

        var codeInterpreter = element.GetFirstToolDefinition(CodeInterpreterType);
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

    private static FileSearchToolResource? GetFileSearchToolResource(this GptComponentMetadata element)
    {
        Throw.IfNull(element);

        var fileSearch = element.GetFirstToolDefinition(FileSearchType);
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

    private static AzureAISearchToolResource? GetAzureAISearchResource(this GptComponentMetadata element)
    {
        Throw.IfNull(element);

        var azureAISearch = element.GetFirstToolDefinition(AzureAISearchType);
        if (azureAISearch is not null)
        {
            string? indexConnectionId = azureAISearch.GetPropertyOrNull<StringDataValue>(InitializablePropertyPath.Create("options.index_connection_id"))?.Value;
            string? indexName = azureAISearch.GetPropertyOrNull<StringDataValue>(InitializablePropertyPath.Create("options.index_name"))?.Value;
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

    private static RecordDataValue? GetFirstToolDefinition(this GptComponentMetadata element, string toolType)
    {
        return element.GetTools().FirstOrDefault(tool => tool.GetTypeValue() == toolType);
    }
    #endregion

}
