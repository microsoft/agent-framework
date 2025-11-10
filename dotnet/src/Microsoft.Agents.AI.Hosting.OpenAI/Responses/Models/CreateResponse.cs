// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Text.Json;
using System.Text.Json.Serialization;

namespace Microsoft.Agents.AI.Hosting.OpenAI.Responses.Models;

/// <summary>
/// Request to create a model response.
/// </summary>
internal sealed class CreateResponse
{
    /// <summary>
    /// Text, image, or file inputs to the model, used to generate a response.
    /// Can be either a simple string (equivalent to a user message) or an array of InputMessage objects.
    /// </summary>
    [JsonPropertyName("input")]
    public required ResponseInput Input { get; init; }

    /// <summary>
    /// The agent to use for generating the response.
    /// </summary>
    [JsonPropertyName("agent")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public AgentReference? Agent { get; init; }

    /// <summary>
    /// Model used to generate the responses.
    /// </summary>
    [JsonPropertyName("model")]
    public string? Model { get; init; }

    /// <summary>
    /// Inserts a system (or developer) message as the first item in the model's context.
    /// </summary>
    [JsonPropertyName("instructions")]
    public string? Instructions { get; init; }

    /// <summary>
    /// An upper bound for the number of tokens that can be generated for a response,
    /// including visible output tokens and reasoning tokens.
    /// </summary>
    [JsonPropertyName("max_output_tokens")]
    public int? MaxOutputTokens { get; init; }

    /// <summary>
    /// Configuration options for reasoning models.
    /// </summary>
    [JsonPropertyName("reasoning")]
    public ReasoningOptions? Reasoning { get; init; }

    /// <summary>
    /// Whether to store the generated model response for later retrieval via API.
    /// </summary>
    [JsonPropertyName("store")]
    public bool? Store { get; init; }

    /// <summary>
    /// If set to true, the model response data will be streamed to the client as it is generated.
    /// </summary>
    [JsonPropertyName("stream")]
    public bool? Stream { get; init; }

    /// <summary>
    /// The unique ID of the previous response to the model. Use this to create multi-turn conversations.
    /// Cannot be used in conjunction with conversation (mutually exclusive).
    /// The previous_response_id determines the conversation thread context - it follows the response chain,
    /// not any explicit conversation. Context is maintained through the chain even if the previous response
    /// was created with a conversation.id.
    /// </summary>
    [JsonPropertyName("previous_response_id")]
    public string? PreviousResponseId { get; init; }

    /// <summary>
    /// What sampling temperature to use, between 0 and 2.
    /// </summary>
    [JsonPropertyName("temperature")]
    public double? Temperature { get; init; }

    /// <summary>
    /// An alternative to sampling with temperature, called nucleus sampling.
    /// </summary>
    [JsonPropertyName("top_p")]
    public double? TopP { get; init; }

    /// <summary>
    /// Whether to allow the model to run tool calls in parallel.
    /// </summary>
    [JsonPropertyName("parallel_tool_calls")]
    public bool? ParallelToolCalls { get; init; }

    /// <summary>
    /// Set of 16 key-value pairs that can be attached to an object.
    /// </summary>
    [JsonPropertyName("metadata")]
    public Dictionary<string, string>? Metadata { get; init; }

    /// <summary>
    /// Specify additional output data to include in the model response.
    /// </summary>
    [JsonPropertyName("include")]
    public List<string>? Include { get; init; }

    /// <summary>
    /// The conversation that this response belongs to. Items from this conversation are prepended
    /// to input_items for this response request.
    /// Can be either a conversation ID (string) or a conversation object with ID and optional metadata.
    /// Input items and output items from this response are automatically added to this conversation after this response completes.
    /// Cannot be used in conjunction with previous_response_id (mutually exclusive).
    /// Use conversation.id for explicit conversation boundaries and starting new threads.
    /// Use previous_response_id for simple linear conversation chaining.
    /// </summary>
    [JsonPropertyName("conversation")]
    public ConversationReference? Conversation { get; init; }

    /// <summary>
    /// Whether to run the model response in the background.
    /// </summary>
    [JsonPropertyName("background")]
    public bool? Background { get; init; }

    /// <summary>
    /// The maximum number of total calls to built-in tools that can be processed in a response.
    /// </summary>
    [JsonPropertyName("max_tool_calls")]
    public int? MaxToolCalls { get; init; }

    /// <summary>
    /// An integer between 0 and 20 specifying the number of most likely tokens to return at each token position.
    /// </summary>
    [JsonPropertyName("top_logprobs")]
    public int? TopLogprobs { get; init; }

    /// <summary>
    /// A stable identifier used to help detect users of your application that may be violating OpenAI's usage policies.
    /// </summary>
    [JsonPropertyName("safety_identifier")]
    public string? SafetyIdentifier { get; init; }

    /// <summary>
    /// Used by OpenAI to cache responses for similar requests to optimize your cache hit rates.
    /// </summary>
    [JsonPropertyName("prompt_cache_key")]
    public string? PromptCacheKey { get; init; }

    /// <summary>
    /// Reference to a prompt template and its variables.
    /// </summary>
    [JsonPropertyName("prompt")]
    public PromptReference? Prompt { get; init; }

    /// <summary>
    /// Specifies the processing type used for serving the request.
    /// If set to 'auto', the request will be processed with the service tier configured in the Project settings.
    /// If set to 'default', the request will be processed with standard pricing and performance.
    /// If set to 'flex' or 'priority', the request will be processed with the corresponding service tier.
    /// </summary>
    [JsonPropertyName("service_tier")]
    public string? ServiceTier { get; init; }

    /// <summary>
    /// Options for streaming responses. Only set this when you set stream: true.
    /// </summary>
    [JsonPropertyName("stream_options")]
    public StreamOptions? StreamOptions { get; init; }

    /// <summary>
    /// The truncation strategy to use for the model response.
    /// </summary>
    [JsonPropertyName("truncation")]
    public string? Truncation { get; init; }

    /// <summary>
    /// This field is being replaced by safety_identifier and prompt_cache_key.
    /// Use prompt_cache_key instead to maintain caching optimizations.
    /// </summary>
    [JsonPropertyName("user")]
    [Obsolete("This field is deprecated. Use safety_identifier and prompt_cache_key instead.")]
    public string? User { get; init; }

    /// <summary>
    /// An array of tools the model may call while generating a response.
    /// </summary>
    [JsonPropertyName("tools")]
    public List<JsonElement>? Tools { get; init; }

    /// <summary>
    /// How the model should select which tool (or tools) to use when generating a response.
    /// </summary>
    [JsonPropertyName("tool_choice")]
    public JsonElement? ToolChoice { get; init; }

    /// <summary>
    /// Configuration options for a text response from the model. Can be plain text or structured JSON data.
    /// </summary>
    [JsonPropertyName("text")]
    public TextConfiguration? Text { get; init; }
}
