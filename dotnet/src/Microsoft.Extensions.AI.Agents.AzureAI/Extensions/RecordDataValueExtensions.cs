// Copyright (c) Microsoft. All rights reserved.
using System.Text.Json;
using Azure.AI.Agents.Persistent;
using Microsoft.Extensions.AI.Agents.AzureAI;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Bot.ObjectModel;

/// <summary>
/// Extension methods for <see cref="RecordDataValue"/>.
/// </summary>
/// <remarks>
/// These are temporary helper methods for use while the single agent definition is being added to Microsoft.Bot.ObjectModel.
/// </remarks>
internal static class RecordDataValueExtensions
{
    internal static AzureAISearchToolDefinition CreateAzureAISearchToolDefinition(this RecordDataValue tool)
    {
        Throw.IfNull(tool);

        return new AzureAISearchToolDefinition();
    }

    internal static AzureFunctionToolDefinition CreateAzureFunctionToolDefinition(this RecordDataValue tool)
    {
        Throw.IfNull(tool);

        StringDataValue? name = tool.GetPropertyOrNull<StringDataValue>(InitializablePropertyPath.Create("id"));
        Throw.IfNull(name?.Value);
        StringDataValue? description = tool.GetPropertyOrNull<StringDataValue>(InitializablePropertyPath.Create("description"));
        Throw.IfNull(description?.Value);
        AzureFunctionBinding inputBinding = tool.GetInputBinding();
        AzureFunctionBinding outputBinding = tool.GetOutputBinding();
        BinaryData parameters = tool.GetParameters();

        return new AzureFunctionToolDefinition(name.Value, description.Value, inputBinding, outputBinding, parameters);
    }

    internal static BingGroundingToolDefinition CreateBingGroundingToolDefinition(this RecordDataValue tool)
    {
        Throw.IfNull(tool);

        TableDataValue? connections = tool.GetPropertyOrNull<TableDataValue>(InitializablePropertyPath.Create("options.tool_connections"));
        Throw.IfNull(connections);

        var searchConfigurations = connections.Values.Select(connection =>
        {
            StringDataValue? connectionId = connection.GetPropertyOrNull<StringDataValue>(InitializablePropertyPath.Create("Value"));
            Throw.IfNull(connectionId?.Value);

            return new BingGroundingSearchConfiguration(connectionId.Value);
        });

        return new BingGroundingToolDefinition(new([.. searchConfigurations]));
    }

    internal static CodeInterpreterToolDefinition CreateCodeInterpreterToolDefinition(this RecordDataValue tool)
    {
        Throw.IfNull(tool);

        return new CodeInterpreterToolDefinition();
    }

    internal static FileSearchToolDefinition CreateFileSearchToolDefinition(this RecordDataValue tool)
    {
        Throw.IfNull(tool);

        return new FileSearchToolDefinition()
        {
            FileSearch = tool.GetFileSearchToolDefinitionDetails()
        };
    }

    internal static FunctionToolDefinition CreateFunctionToolDefinition(this RecordDataValue tool)
    {
        Throw.IfNull(tool);

        string? name = tool.GetPropertyOrNull<StringDataValue>(InitializablePropertyPath.Create("id"))?.Value;
        Throw.IfNull(name);
        string? description = tool.GetPropertyOrNull<StringDataValue>(InitializablePropertyPath.Create("description"))?.Value;
        Throw.IfNull(description);

        BinaryData parameters = tool.GetParameters();

        return new FunctionToolDefinition(name, description, parameters);
    }

    internal static OpenApiToolDefinition CreateOpenApiToolDefinition(this RecordDataValue tool)
    {
        Throw.IfNull(tool);

        string? name = tool.GetPropertyOrNull<StringDataValue>(InitializablePropertyPath.Create("id"))?.Value;
        Throw.IfNull(name);
        string? description = tool.GetPropertyOrNull<StringDataValue>(InitializablePropertyPath.Create("description"))?.Value;
        Throw.IfNull(description);

        BinaryData spec = tool.GetSpecification();
        OpenApiAuthDetails auth = tool.GetOpenApiAuthDetails();

        return new OpenApiToolDefinition(name, description, spec, auth);
    }

    internal static MCPToolDefinition CreateMcpToolDefinition(this RecordDataValue tool)
    {
        Throw.IfNull(tool);

        string? serverLabel = tool.GetPropertyOrNull<StringDataValue>(InitializablePropertyPath.Create("options.server_label"))?.Value;
        Throw.IfNull(serverLabel);
        string? serverUrl = tool.GetPropertyOrNull<StringDataValue>(InitializablePropertyPath.Create("options.server_url"))?.Value;
        Throw.IfNull(serverUrl);

        return new MCPToolDefinition(serverLabel, serverUrl);
    }

    internal static AzureFunctionBinding GetInputBinding(this RecordDataValue agentToolDefinition)
    {
        return agentToolDefinition.GetAzureFunctionBinding("input_binding");
    }

    internal static AzureFunctionBinding GetOutputBinding(this RecordDataValue agentToolDefinition)
    {
        return agentToolDefinition.GetAzureFunctionBinding("output_binding");
    }
    internal static BinaryData GetParameters(this RecordDataValue agentToolDefinition)
    {
        Throw.IfNull(agentToolDefinition);

        var parameters = agentToolDefinition.GetPropertyOrNull<TableDataValue>(InitializablePropertyPath.Create("options.parameters"));
        return parameters is not null ? parameters.CreateParameterSpec() : s_noParams;
    }

#pragma warning disable IL2026 // Members annotated with 'RequiresUnreferencedCodeAttribute' require dynamic access otherwise can break functionality when trimming application code
#pragma warning disable IL3050 // Calling members annotated with 'RequiresDynamicCodeAttribute' may break functionality when AOT compiling.
    internal static BinaryData CreateParameterSpec(this TableDataValue parameters)
    {
        Throw.IfNull(parameters);

        JsonSchemaFunctionParameters parameterSpec = new();
        foreach (var parameter in parameters.Values)
        {
            bool isRequired = parameter.GetPropertyOrNull<BooleanDataValue>(InitializablePropertyPath.Create("required"))?.Value ?? false;
            string? name = parameter.GetPropertyOrNull<StringDataValue>(InitializablePropertyPath.Create("name"))?.Value;
            string? type = parameter.GetPropertyOrNull<StringDataValue>(InitializablePropertyPath.Create("type"))?.Value;
            string? description = parameter.GetPropertyOrNull<StringDataValue>(InitializablePropertyPath.Create("description"))?.Value;

            if (string.IsNullOrEmpty(name) || string.IsNullOrEmpty(type))
            {
                throw new ArgumentException("The option keys 'queueName' and 'type' are required for a parameter.");
            }

            if (isRequired)
            {
                parameterSpec.Required.Add(name!);
            }
            parameterSpec.Properties.Add(name!, JsonSerializer.Deserialize<JsonElement>($"{{ \"type\": \"{type}\", \"description\": \"{description}\" }}"));
        }

        byte[] data = JsonSerializer.SerializeToUtf8Bytes(parameterSpec, typeof(JsonSchemaFunctionParameters));
        return new BinaryData(data);
    }
#pragma warning restore IL3050 // Calling members annotated with 'RequiresDynamicCodeAttribute' may break functionality when AOT compiling.
#pragma warning restore IL2026 // Members annotated with 'RequiresUnreferencedCodeAttribute' require dynamic access otherwise can break functionality when trimming application code

    internal static FileSearchToolDefinitionDetails GetFileSearchToolDefinitionDetails(this RecordDataValue agentToolDefinition)
    {
        var details = new FileSearchToolDefinitionDetails();
        var maxNumResults = agentToolDefinition.GetPropertyOrNull<NumberDataValue>(InitializablePropertyPath.Create("max_num_results"))?.Value;
        if (maxNumResults is not null && maxNumResults > 0)
        {
            details.MaxNumResults = ((int?)maxNumResults);
        }

        FileSearchRankingOptions? rankingOptions = agentToolDefinition.GetFileSearchRankingOptions();
        if (rankingOptions is not null)
        {
            details.RankingOptions = rankingOptions;
        }

        return details;
    }

    internal static BinaryData GetSpecification(this RecordDataValue agentToolDefinition)
    {
        Throw.IfNull(agentToolDefinition);

        try
        {
            var specificationStr = agentToolDefinition.GetPropertyOrNull<StringDataValue>(InitializablePropertyPath.Create("options.specification"));
            if (specificationStr?.Value is not null)
            {
                return new BinaryData(specificationStr.Value);
            }
        }
        catch (InvalidCastException)
        {
            // Ignore and try next
        }

        var specificationRec = agentToolDefinition.GetPropertyOrNull<RecordDataValue>(InitializablePropertyPath.Create("options.specification"));
        if (specificationRec is not null)
        {
#pragma warning disable IL2026 // Members annotated with 'RequiresUnreferencedCodeAttribute' require dynamic access otherwise can break functionality when trimming application code
#pragma warning disable IL3050 // Calling members annotated with 'RequiresDynamicCodeAttribute' may break functionality when AOT compiling.
            var json = JsonSerializer.Serialize(specificationRec, ElementSerializer.CreateOptions());
#pragma warning restore IL3050 // Calling members annotated with 'RequiresDynamicCodeAttribute' may break functionality when AOT compiling.
#pragma warning restore IL2026 // Members annotated with 'RequiresUnreferencedCodeAttribute' require dynamic access otherwise can break functionality when trimming application code
            return new BinaryData(json);
        }

        throw new InvalidOperationException("The OpenAPI tool definition must include a specification in the options.");
    }

    internal static OpenApiAuthDetails GetOpenApiAuthDetails(this RecordDataValue agentToolDefinition)
    {
        var connectionId = agentToolDefinition.GetPropertyOrNull<StringDataValue>(InitializablePropertyPath.Create("options.connection_id"));
        if (connectionId?.Value is not null)
        {
            return new OpenApiConnectionAuthDetails(new OpenApiConnectionSecurityScheme(connectionId.Value));
        }

        var audience = agentToolDefinition.GetPropertyOrNull<StringDataValue>(InitializablePropertyPath.Create("options.audience"));
        if (audience?.Value is not null)
        {
            return new OpenApiManagedAuthDetails(new OpenApiManagedSecurityScheme(audience.Value));
        }

        return new OpenApiAnonymousAuthDetails();
    }

    internal static List<string>? GetVectorStoreIds(this RecordDataValue agentToolDefinition)
    {
        var toolConnections = agentToolDefinition.GetPropertyOrNull<TableDataValue>(InitializablePropertyPath.Create("options.vector_store_ids"));
        return toolConnections is not null
            ? [.. toolConnections.Values.Select(connection => connection.GetPropertyOrNull<StringDataValue>(InitializablePropertyPath.Create("Value"))?.Value)]
            : null;
    }

    internal static List<string>? GetFileIds(this RecordDataValue agentToolDefinition)
    {
        var fileIds = agentToolDefinition.GetPropertyOrNull<TableDataValue>(InitializablePropertyPath.Create("options.file_ids"));
        return fileIds is not null
            ? [.. fileIds.Values.Select(fileId => fileId.GetPropertyOrNull<StringDataValue>(InitializablePropertyPath.Create("Value"))?.Value)]
            : null;
    }

    internal static List<VectorStoreDataSource>? GetDataSources(this RecordDataValue agentToolDefinition)
    {
        var dataSources = agentToolDefinition.GetPropertyOrNull<TableDataValue>(InitializablePropertyPath.Create("options.data_sources"));
        return dataSources is not null
            ? dataSources.Values.Select(dataSource => dataSource.CreateDataSource()).ToList()
            : null;
    }

    internal static VectorStoreDataSource CreateDataSource(this RecordDataValue value)
    {
        Throw.IfNull(value);

        string? assetIdentifier = value.GetPropertyOrNull<StringDataValue>(InitializablePropertyPath.Create("asset_identifier"))?.Value;
        Throw.IfNullOrEmpty(assetIdentifier);

        string? assetType = value.GetPropertyOrNull<StringDataValue>(InitializablePropertyPath.Create("asset_type"))?.Value;
        Throw.IfNullOrEmpty(assetType);

        return new VectorStoreDataSource(assetIdentifier, new VectorStoreDataSourceAssetType(assetType));
    }
    internal static IList<VectorStoreConfigurations>? GetVectorStoreConfigurations(this RecordDataValue agentToolDefinition)
    {
        var dataSources = agentToolDefinition.GetPropertyOrNull<TableDataValue>(InitializablePropertyPath.Create("options.configurations"));
        return dataSources is not null ? dataSources.Values.Select(value => value.CreateVectorStoreConfiguration()).ToList() : null;
    }

    internal static VectorStoreConfigurations CreateVectorStoreConfiguration(this RecordDataValue value)
    {
        var storeName = value.GetPropertyOrNull<StringDataValue>(InitializablePropertyPath.Create("store_name"))?.Value;
        Throw.IfNullOrEmpty(storeName);

        var dataSources = value.GetDataSources();
        Throw.IfNull(dataSources);

        return new VectorStoreConfigurations(storeName, new VectorStoreConfiguration(dataSources));
    }

    private static AzureFunctionBinding GetAzureFunctionBinding(this RecordDataValue agentToolDefinition, string bindingType)
    {
        Throw.IfNull(agentToolDefinition);

        var options = agentToolDefinition.GetPropertyOrNull<RecordDataValue>(InitializablePropertyPath.Create("options"));
        Throw.IfNull(options);

        var binding = options.GetPropertyOrNull<RecordDataValue>(InitializablePropertyPath.Create(bindingType));
        Throw.IfNull(binding);

        var storageServiceEndpoint = binding.GetPropertyOrNull<StringDataValue>(InitializablePropertyPath.Create("storage_service_endpoint"));
        Throw.IfNull(storageServiceEndpoint?.Value);

        var queueName = binding.GetPropertyOrNull<StringDataValue>(InitializablePropertyPath.Create("queue_name"));
        Throw.IfNull(queueName?.Value);

        return new AzureFunctionBinding(new AzureFunctionStorageQueue(storageServiceEndpoint.Value, queueName.Value));
    }

    internal static int? GetTopK(this RecordDataValue agentToolDefinition)
    {
        Throw.IfNull(agentToolDefinition);

        return (int?)agentToolDefinition.GetPropertyOrNull<NumberDataValue>(InitializablePropertyPath.Create("options.top_k"))?.Value;
    }

    internal static string? GetFilter(this RecordDataValue agentToolDefinition)
    {
        Throw.IfNull(agentToolDefinition);

        return agentToolDefinition.GetPropertyOrNull<StringDataValue>(InitializablePropertyPath.Create("options.filter"))?.Value;
    }

    internal static AzureAISearchQueryType? GetAzureAISearchQueryType(this RecordDataValue agentToolDefinition)
    {
        return agentToolDefinition.GetPropertyOrNull<StringDataValue>(InitializablePropertyPath.Create("options.query_type"))?.Value is string queryType
            ? new AzureAISearchQueryType(queryType)
            : null;
    }

    internal static FileSearchRankingOptions? GetFileSearchRankingOptions(this RecordDataValue agentToolDefinition)
    {
        Throw.IfNull(agentToolDefinition);

        string? ranker = agentToolDefinition.GetPropertyOrNull<StringDataValue>(InitializablePropertyPath.Create("ranker"))?.Value;
        decimal? scoreThreshold = agentToolDefinition.GetPropertyOrNull<NumberDataValue>(InitializablePropertyPath.Create("score_threshold"))?.Value;

        if (ranker is not null && scoreThreshold is not null)
        {
            return new FileSearchRankingOptions(ranker, (float)scoreThreshold!);
        }

        return null;
    }

    internal static List<string> GetToolConnections(this RecordDataValue agentToolDefinition)
    {
        Throw.IfNull(agentToolDefinition);

        var toolConnections = agentToolDefinition.GetPropertyOrNull<TableDataValue>(InitializablePropertyPath.Create("options.tool_connections"));
        Throw.IfNull(toolConnections);

        return [.. toolConnections.Values.Select(connection => connection.GetPropertyOrNull<StringDataValue>(InitializablePropertyPath.Create("Value"))?.Value)];
    }

    private static readonly BinaryData s_noParams = new("{\"type\":\"object\",\"properties\":{}}");
}
