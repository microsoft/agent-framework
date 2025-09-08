// Copyright (c) Microsoft. All rights reserved.

using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;
using System.Text.Json.Serialization;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.AI.Agents;
using Microsoft.Extensions.Logging;
using Microsoft.Shared.Diagnostics;
using OpenAI.Assistants;

namespace OpenAI;

/// <summary>
/// Provides extension methods for OpenAI <see cref="AssistantClient"/>
/// to simplify the creation of AI agents that work with OpenAI services.
/// </summary>
/// <remarks>
/// These extensions bridge the gap between OpenAI SDK client objects and the Microsoft Extensions AI Agent framework,
/// allowing developers to easily create AI agents that leverage OpenAI's chat completion and response services.
/// The methods handle the conversion from OpenAI clients to <see cref="IChatClient"/> instances and then wrap them
/// in <see cref="ChatClientAgent"/> objects that implement the <see cref="AIAgent"/> interface.
/// </remarks>
public static class OpenAIAssistantClientExtensions
{
    /// <summary>Key into AdditionalProperties used to store a strict option.</summary>
    private const string StrictKey = "strictJsonSchema";

    /// <summary>
    /// Creates an AI agent from an <see cref="AssistantClient"/> using the OpenAI Assistant API.
    /// </summary>
    /// <param name="client">The OpenAI <see cref="AssistantClient" /> to use for the agent.</param>
    /// <param name="model">The model identifier to use (e.g., "gpt-4").</param>
    /// <param name="instructions">Optional system instructions that define the agent's behavior and personality.</param>
    /// <param name="name">Optional name for the agent for identification purposes.</param>
    /// <param name="description">Optional description of the agent's capabilities and purpose.</param>
    /// <param name="tools">Optional collection of AI tools that the agent can use during conversations.</param>
    /// <param name="loggerFactory">Optional logger factory for enabling logging within the agent.</param>
    /// <returns>An <see cref="AIAgent"/> instance backed by the OpenAI Assistant service.</returns>
    /// <exception cref="ArgumentNullException">Thrown when <paramref name="client"/> or <paramref name="model"/> is <see langword="null"/>.</exception>
    /// <exception cref="ArgumentException">Thrown when <paramref name="model"/> is empty or whitespace.</exception>
    public static AIAgent CreateAIAgent(this AssistantClient client, string model, string? instructions = null, string? name = null, string? description = null, IList<AITool>? tools = null, ILoggerFactory? loggerFactory = null)
    {
        return client.CreateAIAgent(
            model,
            new ChatClientAgentOptions()
            {
                Name = name,
                Description = description,
                Instructions = instructions,
                ChatOptions = tools is null ? null : new ChatOptions()
                {
                    Tools = tools,
                }
            },
            loggerFactory);
    }

    /// <summary>
    /// Creates an AI agent from an <see cref="AssistantClient"/> using the OpenAI Assistant API.
    /// </summary>
    /// <param name="client">The OpenAI <see cref="AssistantClient" /> to use for the agent.</param>
    /// <param name="model">The model identifier to use (e.g., "gpt-4").</param>
    /// <param name="options">Full set of options to configure the agent.</param>
    /// <param name="loggerFactory">Optional logger factory for enabling logging within the agent.</param>
    /// <returns>An <see cref="AIAgent"/> instance backed by the OpenAI Assistant service.</returns>
    /// <exception cref="ArgumentNullException">Thrown when <paramref name="client"/> or <paramref name="model"/> or <paramref name="options"/> is <see langword="null"/>.</exception>
    /// <exception cref="ArgumentException">Thrown when <paramref name="model"/> is empty or whitespace.</exception>
    public static AIAgent CreateAIAgent(this AssistantClient client, string model, ChatClientAgentOptions options, ILoggerFactory? loggerFactory = null)
    {
        Throw.IfNull(client);
        Throw.IfNullOrEmpty(model);
        Throw.IfNull(options);

        var assistantOptions = new AssistantCreationOptions()
        {
            Name = options.Name,
            Description = options.Description,
            Instructions = options.Instructions,
        };

        if (options.ChatOptions?.Tools is not null)
        {
            foreach (AITool tool in options.ChatOptions.Tools)
            {
                switch (tool)
                {
                    // Attempting to set the tools at the agent level throws
                    // https://github.com/dotnet/extensions/issues/6743
                    //case AIFunction aiFunction:
                    //    assistantOptions.Tools.Add(ToOpenAIAssistantsFunctionToolDefinition(aiFunction));
                    //    break;

                    case HostedCodeInterpreterTool:
                        var codeInterpreterToolDefinition = new CodeInterpreterToolDefinition();
                        assistantOptions.Tools.Add(codeInterpreterToolDefinition);
                        break;
                }
            }
        }

        var assistantCreateResult = client.CreateAssistant(model, assistantOptions);
        var assistantId = assistantCreateResult.Value.Id;

        var agentOptions = new ChatClientAgentOptions()
        {
            Id = assistantId,
            Name = options.Name,
            Description = options.Description,
            Instructions = options.Instructions,
            ChatOptions = options.ChatOptions?.Tools is null ? null : new ChatOptions()
            {
                Tools = options.ChatOptions.Tools,
            }
        };

#pragma warning disable CA2000 // Dispose objects before losing scope
        var chatClient = client.AsIChatClient(assistantId);
#pragma warning restore CA2000 // Dispose objects before losing scope
        return new ChatClientAgent(chatClient, agentOptions, loggerFactory);
    }

    /// <summary>
    /// Creates an AI agent from an <see cref="AssistantClient"/> using the OpenAI Assistant API.
    /// </summary>
    /// <param name="client">The OpenAI <see cref="AssistantClient" /> to use for the agent.</param>
    /// <param name="model">The model identifier to use (e.g., "gpt-4").</param>
    /// <param name="instructions">Optional system instructions that define the agent's behavior and personality.</param>
    /// <param name="name">Optional name for the agent for identification purposes.</param>
    /// <param name="description">Optional description of the agent's capabilities and purpose.</param>
    /// <param name="tools">Optional collection of AI tools that the agent can use during conversations.</param>
    /// <param name="loggerFactory">Optional logger factory for enabling logging within the agent.</param>
    /// <returns>An <see cref="AIAgent"/> instance backed by the OpenAI Assistant service.</returns>
    /// <exception cref="ArgumentNullException">Thrown when <paramref name="client"/> or <paramref name="model"/> is <see langword="null"/>.</exception>
    /// <exception cref="ArgumentException">Thrown when <paramref name="model"/> is empty or whitespace.</exception>
    public static async Task<AIAgent> CreateAIAgentAsync(this AssistantClient client, string model, string? instructions = null, string? name = null, string? description = null, IList<AITool>? tools = null, ILoggerFactory? loggerFactory = null)
    {
        return await client.CreateAIAgentAsync(
            model,
            new ChatClientAgentOptions()
            {
                Name = name,
                Description = description,
                Instructions = instructions,
                ChatOptions = tools is null ? null : new ChatOptions()
                {
                    Tools = tools,
                }
            },
            loggerFactory).ConfigureAwait(false);
    }

    /// <summary>
    /// Creates an AI agent from an <see cref="AssistantClient"/> using the OpenAI Assistant API.
    /// </summary>
    /// <param name="client">The OpenAI <see cref="AssistantClient" /> to use for the agent.</param>
    /// <param name="model">The model identifier to use (e.g., "gpt-4").</param>
    /// <param name="options">Full set of options to configure the agent.</param>
    /// <param name="loggerFactory">Optional logger factory for enabling logging within the agent.</param>
    /// <returns>An <see cref="AIAgent"/> instance backed by the OpenAI Assistant service.</returns>
    /// <exception cref="ArgumentNullException">Thrown when <paramref name="client"/> or <paramref name="model"/> is <see langword="null"/>.</exception>
    /// <exception cref="ArgumentException">Thrown when <paramref name="model"/> is empty or whitespace.</exception>
    public static async Task<AIAgent> CreateAIAgentAsync(this AssistantClient client, string model, ChatClientAgentOptions options, ILoggerFactory? loggerFactory = null)
    {
        Throw.IfNull(client);
        Throw.IfNull(model);
        Throw.IfNull(options);

        var assistantOptions = new AssistantCreationOptions()
        {
            Name = options.Name,
            Description = options.Description,
            Instructions = options.Instructions,
        };

        if (options.ChatOptions?.Tools is not null)
        {
            foreach (AITool tool in options.ChatOptions.Tools)
            {
                switch (tool)
                {
                    // Attempting to set the tools at the agent level throws
                    // https://github.com/dotnet/extensions/issues/6743
                    //case AIFunction aiFunction:
                    //    assistantOptions.Tools.Add(ToOpenAIAssistantsFunctionToolDefinition(aiFunction));
                    //    break;

                    case HostedCodeInterpreterTool:
                        var codeInterpreterToolDefinition = new CodeInterpreterToolDefinition();
                        assistantOptions.Tools.Add(codeInterpreterToolDefinition);
                        break;
                }
            }
        }

        var assistantCreateResult = await client.CreateAssistantAsync(model, assistantOptions).ConfigureAwait(false);
        var assistantId = assistantCreateResult.Value.Id;

        var agentOptions = new ChatClientAgentOptions()
        {
            Id = assistantId,
            Name = options.Name,
            Description = options.Description,
            Instructions = options.Instructions,
            ChatOptions = options.ChatOptions?.Tools is null ? null : new ChatOptions()
            {
                Tools = options.ChatOptions.Tools,
            }
        };

#pragma warning disable CA2000 // Dispose objects before losing scope
        var chatClient = client.AsNewIChatClient(assistantId);
#pragma warning restore CA2000 // Dispose objects before losing scope
        return new ChatClientAgent(chatClient, agentOptions, loggerFactory);
    }

    /// <summary>Converts an Extensions function to an OpenAI assistants function tool.</summary>
    private static FunctionToolDefinition ToOpenAIAssistantsFunctionToolDefinition(AIFunction aiFunction, ChatOptions? options = null)
    {
        bool? strict =
            HasStrict(aiFunction.AdditionalProperties) ??
            HasStrict(options?.AdditionalProperties);

        return new FunctionToolDefinition(aiFunction.Name)
        {
            Description = aiFunction.Description,
            Parameters = ToOpenAIFunctionParameters(aiFunction, strict),
            StrictParameterSchemaEnabled = strict,
        };
    }

    /// <summary>Extracts from an <see cref="AIFunction"/> the parameters and strictness setting for use with OpenAI's APIs.</summary>
    private static BinaryData ToOpenAIFunctionParameters(AIFunction aiFunction, bool? strict)
    {
        // Perform any desirable transformations on the function's JSON schema, if it'll be used in a strict setting.
        JsonElement jsonSchema = strict is true ?
            StrictSchemaTransformCache.GetOrCreateTransformedSchema(aiFunction) :
            aiFunction.JsonSchema;

        // Roundtrip the schema through the ToolJson model type to remove extra properties
        // and force missing ones into existence, then return the serialized UTF8 bytes as BinaryData.
        var tool = jsonSchema.Deserialize(OpenAIJsonContext.Default.ToolJson)!;
        var functionParameters = BinaryData.FromBytes(JsonSerializer.SerializeToUtf8Bytes(tool, OpenAIJsonContext.Default.ToolJson));

        return functionParameters;
    }

    /// <summary>Gets whether the properties specify that strict schema handling is desired.</summary>
    private static bool? HasStrict(IReadOnlyDictionary<string, object?>? additionalProperties) =>
        additionalProperties?.TryGetValue(StrictKey, out object? strictObj) is true &&
        strictObj is bool strictValue ?
        strictValue : null;

    private static AIJsonSchemaTransformCache StrictSchemaTransformCache { get; } = new(new()
    {
        DisallowAdditionalProperties = true,
        ConvertBooleanSchemas = true,
        MoveDefaultKeywordToDescription = true,
        RequireAllProperties = true,
        TransformSchemaNode = (ctx, node) =>
        {
            // Move content from common but unsupported properties to description. In particular, we focus on properties that
            // the AIJsonUtilities schema generator might produce and/or that are explicitly mentioned in the OpenAI documentation.

            if (node is JsonObject schemaObj)
            {
                StringBuilder? additionalDescription = null;

                ReadOnlySpan<string> unsupportedProperties =
                [
                    // Produced by AIJsonUtilities but not in allow list at https://platform.openai.com/docs/guides/structured-outputs#supported-properties:
                    "contentEncoding", "contentMediaType", "not",

                    // Explicitly mentioned at https://platform.openai.com/docs/guides/structured-outputs?api-mode=responses#key-ordering as being unsupported with some models:
                    "minLength", "maxLength", "pattern", "format",
                    "minimum", "maximum", "multipleOf",
                    "patternProperties",
                    "minItems", "maxItems",

                    // Explicitly mentioned at https://learn.microsoft.com/azure/ai-services/openai/how-to/structured-outputs?pivots=programming-language-csharp&tabs=python-secure%2Cdotnet-entra-id#unsupported-type-specific-keywords
                    // as being unsupported with Azure OpenAI:
                    "unevaluatedProperties", "propertyNames", "minProperties", "maxProperties",
                    "unevaluatedItems", "contains", "minContains", "maxContains", "uniqueItems",
                ];

                foreach (string propName in unsupportedProperties)
                {
                    if (schemaObj[propName] is { } propNode)
                    {
                        _ = schemaObj.Remove(propName);
                        AppendLine(ref additionalDescription, propName, propNode);
                    }
                }

                if (additionalDescription is not null)
                {
                    schemaObj["description"] = schemaObj["description"] is { } descriptionNode && descriptionNode.GetValueKind() == JsonValueKind.String ?
                        $"{descriptionNode.GetValue<string>()}{Environment.NewLine}{additionalDescription}" :
                        additionalDescription.ToString();
                }

                return node;

                static void AppendLine(ref StringBuilder? sb, string propName, JsonNode propNode)
                {
                    sb ??= new();

                    if (sb.Length > 0)
                    {
                        _ = sb.AppendLine();
                    }

                    _ = sb.Append(propName).Append(": ").Append(propNode);
                }
            }

            return node;
        },
    });

    /// <summary>Used to create the JSON payload for an OpenAI tool description.</summary>
    internal sealed class ToolJson
    {
        [JsonPropertyName("type")]
        public string Type { get; set; } = "object";

        [JsonPropertyName("required")]
        public HashSet<string> Required { get; set; } = [];

        [JsonPropertyName("properties")]
        public Dictionary<string, JsonElement> Properties { get; set; } = [];

        [JsonPropertyName("additionalProperties")]
        public bool AdditionalProperties { get; set; }
    }
}

/// <summary>Source-generated JSON type information for use by all OpenAI implementations.</summary>
[JsonSourceGenerationOptions(JsonSerializerDefaults.Web,
    UseStringEnumConverter = true,
    DefaultIgnoreCondition = JsonIgnoreCondition.WhenWritingNull,
    WriteIndented = true)]
[JsonSerializable(typeof(OpenAIAssistantClientExtensions.ToolJson))]
[JsonSerializable(typeof(IDictionary<string, object?>))]
[JsonSerializable(typeof(string[]))]
[JsonSerializable(typeof(JsonElement))]
internal sealed partial class OpenAIJsonContext : JsonSerializerContext;
