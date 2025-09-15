// Copyright (c) Microsoft. All rights reserved.
using System.Text.Json;
using Azure.AI.Agents.Persistent;
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

    /*
    private static BingGroundingToolDefinition CreateBingGroundingToolDefinition(RecordDataValue tool, AIProjectClient projectClient)
    {
        //Throw.IfNull(tool);

        IEnumerable<string> connectionIds = projectClient.GetConnectionIds(tool);
        BingGroundingSearchToolParameters bingToolParameters = new([new BingGroundingSearchConfiguration(connectionIds.Single())]);

        return new BingGroundingToolDefinition(bingToolParameters);
    }*/

    internal static CodeInterpreterToolDefinition CreateCodeInterpreterToolDefinition(this RecordDataValue tool)
    {
        Throw.IfNull(tool);

        return new CodeInterpreterToolDefinition();
    }

    internal static FileSearchToolDefinition CreateFileSearchToolDefinition(RecordDataValue tool)
    {
        Throw.IfNull(tool);

        return new FileSearchToolDefinition()
        {
            //FileSearch = tool.GetFileSearchToolDefinitionDetails()
        };
    }

    internal static FunctionToolDefinition CreateFunctionToolDefinition(this RecordDataValue tool)
    {
        Throw.IfNull(tool);

        StringDataValue? name = tool.GetPropertyOrNull<StringDataValue>(InitializablePropertyPath.Create("id"));
        Throw.IfNull(name?.Value);
        StringDataValue? description = tool.GetPropertyOrNull<StringDataValue>(InitializablePropertyPath.Create("description"));
        Throw.IfNull(description?.Value);

        BinaryData parameters = tool.GetParameters();

        return new FunctionToolDefinition(name.Value, description.Value, parameters);
    }

    internal static OpenApiToolDefinition CreateOpenApiToolDefinition(this RecordDataValue tool)
    {
        Throw.IfNull(tool);

        StringDataValue? name = tool.GetPropertyOrNull<StringDataValue>(InitializablePropertyPath.Create("id"));
        Throw.IfNull(name?.Value);
        StringDataValue? description = tool.GetPropertyOrNull<StringDataValue>(InitializablePropertyPath.Create("description"));
        Throw.IfNull(description?.Value);

        BinaryData spec = tool.GetSpecification();
        OpenApiAuthDetails auth = tool.GetOpenApiAuthDetails();

        return new OpenApiToolDefinition(name.Value, description.Value, spec, auth);
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
        //var parameters = agentToolDefinition.GetPropertyOrNull<ListDataValue>(InitializablePropertyPath.Create("options.parameters"));
        //return parameters is not null ? CreateParameterSpec(parameters) : s_noParams;
        return s_noParams;
    }

    /*
    internal static BinaryData CreateParameterSpec(List<object> parameters)
    {
        JsonSchemaFunctionParameters parameterSpec = new();
        foreach (var parameter in parameters)
        {
            var parameterProps = parameter as Dictionary<object, object>;
            if (parameterProps is not null)
            {
                bool isRequired = parameterProps.TryGetValue("required", out var requiredValue) && requiredValue is string requiredString && requiredString.Equals("true", StringComparison.OrdinalIgnoreCase);
                string? queueName = parameterProps.TryGetValue("queueName", out var nameValue) && nameValue is string nameString ? nameString : null;
                string? type = parameterProps.TryGetValue("type", out var typeValue) && typeValue is string typeString ? typeString : null;
                string? description = parameterProps.TryGetValue("description", out var descriptionValue) && descriptionValue is string descriptionString ? descriptionString : string.Empty;

                if (string.IsNullOrEmpty(queueName) || string.IsNullOrEmpty(type))
                {
                    throw new ArgumentException("The option keys 'queueName' and 'type' are required for a parameter.");
                }

                if (isRequired)
                {
                    parameterSpec.Required.Add(queueName!);
                }
                parameterSpec.Properties.Add(queueName!, KernelJsonSchema.Parse($"{{ \"type\": \"{type}\", \"description\": \"{description}\" }}"));
            }
        }

        return BinaryData.FromObjectAsJson(parameterSpec);
    }

    internal static FileSearchToolDefinitionDetails GetFileSearchToolDefinitionDetails(this RecordDataValue agentToolDefinition)
    {
        var details = new FileSearchToolDefinitionDetails();
        var maxNumResults = agentToolDefinition.GetOption<int?>("max_num_results");
        if (maxNumResults is not null && maxNumResults > 0)
        {
            details.MaxNumResults = maxNumResults;
        }

        FileSearchRankingOptions? rankingOptions = agentToolDefinition.GetFileSearchRankingOptions();
        if (rankingOptions is not null)
        {
            details.RankingOptions = rankingOptions;
        }

        return details;
    }
    */

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

    /*
    internal static List<string>? GetVectorStoreIds(this RecordDataValue agentToolDefinition)
    {
        return agentToolDefinition.GetOption<List<object>>("vector_store_ids")?.Select(id => $"{id}").ToList();
    }

    internal static List<string>? GetFileIds(this RecordDataValue agentToolDefinition)
    {
        return agentToolDefinition.GetOption<List<object>>("file_ids")?.Select(id => id.ToString()!).ToList();
    }

    internal static List<VectorStoreDataSource>? GetDataSources(this RecordDataValue agentToolDefinition)
    {
        var dataSources = agentToolDefinition.GetOption<List<object>?>("data_sources");
        return dataSources is not null ? CreateDataSources(dataSources) : null;
    }

    internal static List<VectorStoreDataSource> CreateDataSources(List<object> values)
    {
        List<VectorStoreDataSource> dataSources = [];
        foreach (var value in values)
        {
            if (value is Dictionary<object, object> dataSourceDict)
            {
                string? assetIdentifier = dataSourceDict.TryGetValue("asset_identifier", out var identifierValue) && identifierValue is string identifierString ? identifierString : null;
                string? assetType = dataSourceDict.TryGetValue("asset_type", out var typeValue) && typeValue is string typeString ? typeString : null;

                if (string.IsNullOrEmpty(assetIdentifier) || string.IsNullOrEmpty(assetType))
                {
                    throw new ArgumentException("The option keys 'asset_identifier' and 'asset_type' are required for a vector store data source.");
                }

                dataSources.Add(new VectorStoreDataSource(assetIdentifier, new VectorStoreDataSourceAssetType(assetType)));
            }
        }

        return dataSources;
    }

    internal static IList<VectorStoreConfigurations>? GetVectorStoreConfigurations(this RecordDataValue agentToolDefinition)
    {
        var dataSources = agentToolDefinition.GetOption<List<object>?>("configurations");
        return dataSources is not null ? CreateVectorStoreConfigurations(dataSources) : null;
    }

    internal static List<VectorStoreConfigurations> CreateVectorStoreConfigurations(List<object> values)
    {
        List<VectorStoreConfigurations> configurations = [];
        foreach (var value in values)
        {
            if (value is Dictionary<object, object> configurationDict)
            {
                var storeName = configurationDict.TryGetValue("store_name", out var storeNameValue) && storeNameValue is string storeNameString ? storeNameString : null;
                var dataSources = configurationDict.TryGetValue("data_sources", out var dataSourceValue) && dataSourceValue is List<object> dataSourceList ? CreateDataSources(dataSourceList) : null;

                if (string.IsNullOrEmpty(storeName) || dataSources is null)
                {
                    throw new ArgumentException("The option keys 'store_name' and 'data_sources' are required for a vector store configuration.");
                }

                configurations.Add(new VectorStoreConfigurations(storeName, new VectorStoreConfiguration(dataSources)));
            }
        }

        return configurations;
    }
    */

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

    /*
    internal static int? GetTopK(this RecordDataValue agentToolDefinition)
    {
        return agentToolDefinition.Options?.TryGetValue("top_k", out var topKValue) ?? false
            ? int.Parse((string)topKValue!)
            : null;
    }

    internal static string? GetFilter(this RecordDataValue agentToolDefinition)
    {
        return agentToolDefinition.Options?.TryGetValue("filter", out var filterValue) ?? false
            ? filterValue as string
            : null;
    }

    internal static AzureAISearchQueryType? GetAzureAISearchQueryType(this RecordDataValue agentToolDefinition)
    {
        return agentToolDefinition.Options?.TryGetValue("query_type", out var queryTypeValue) ?? false
            ? new AzureAISearchQueryType(queryTypeValue as string)
            : null;
    }

    private static FileSearchRankingOptions? GetFileSearchRankingOptions(this RecordDataValue agentToolDefinition)
    {
        string? ranker = agentToolDefinition.GetOption<string>("ranker");
        float? scoreThreshold = agentToolDefinition.GetOption<float>("score_threshold");

        if (ranker is not null && scoreThreshold is not null)
        {
            return new FileSearchRankingOptions(ranker, (float)scoreThreshold!);
        }

        return null;
    }

    internal static List<string> GetToolConnections(this RecordDataValue agentToolDefinition)
    {
        Verify.NotNull(agentToolDefinition.Options);

        List<object> toolConnections = agentToolDefinition.GetRequiredOption<List<object>>("tool_connections");

        return [.. toolConnections.Select(connectionId => $"{connectionId}")];
    }

    private static T GetRequiredOption<T>(this RecordDataValue agentToolDefinition, string key)
    {
        Verify.NotNull(agentToolDefinition);
        Verify.NotNull(agentToolDefinition.Options);
        Verify.NotNull(key);

        if (agentToolDefinition.Options?.TryGetValue(key, out var value) ?? false)
        {
            if (value == null)
            {
                throw new ArgumentNullException($"The option key '{key}' must be a non null value.");
            }

            if (value is T expectedValue)
            {
                return expectedValue;
            }
            throw new InvalidCastException($"The option key '{key}' value must be of type '{typeof(T)}' but is '{value.GetType()}'.");
        }

        throw new ArgumentException($"The option key '{key}' was not found.");
    }
    */

    private static readonly BinaryData s_noParams = new("{\"type\":\"object\",\"properties\":{}}");
}
