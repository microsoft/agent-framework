// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Text.Json.Serialization;

namespace Microsoft.Agents.AI.Hosting.OpenAI.ChatCompletions.Models;

/// <summary>
/// Request to create a chat completion.
/// </summary>
internal sealed record CreateChatCompletion
{
    /// <summary>
    /// A list of messages comprising the conversation so far.
    /// </summary>
    [JsonPropertyName("messages")]
    [JsonRequired]
    public required IList<ChatCompletionRequestMessage> Messages { get; set; }

    /// <summary>
    /// Model ID used to generate the response, like `gpt-4o` or `o3`.
    /// </summary>
    [JsonPropertyName("model")]
    [JsonRequired]
    public required string Model { get; set; }

    /// <summary>
    /// Parameters for audio output. Required when audio output is requested with modalities: ["audio"].
    /// </summary>
    [JsonPropertyName("audio")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public object? Audio { get; set; }

    /// <summary>
    /// Number between -2.0 and 2.0. Positive values penalize new tokens based on their existing frequency in the text so far.
    /// </summary>
    [JsonPropertyName("frequency_penalty")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public float? FrequencyPenalty { get; set; }

    /// <summary>
    /// Deprecated in favor of tool_choice. Controls which (if any) function is called by the model.
    /// </summary>
    [JsonPropertyName("function_call")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    [Obsolete("Deprecated in favor of ToolChoice.")]
    public object? FunctionCall { get; set; }

    /// <summary>
    /// Deprecated in favor of tools. A list of functions the model may generate JSON inputs for.
    /// </summary>
    [JsonPropertyName("functions")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    [Obsolete("Deprecated in favor of Tools.")]
    public IList<object>? Functions { get; set; }

    /// <summary>
    /// Modify the likelihood of specified tokens appearing in the completion.
    /// </summary>
    [JsonPropertyName("logit_bias")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public Dictionary<string, int>? LogitBias { get; set; }

    /// <summary>
    /// Whether to return log probabilities of the output tokens or not.
    /// </summary>
    [JsonPropertyName("logprobs")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public bool? Logprobs { get; set; }

    /// <summary>
    /// An upper bound for the number of tokens that can be generated for a completion, including visible output tokens and reasoning tokens.
    /// </summary>
    [JsonPropertyName("max_completion_tokens")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public int? MaxCompletionTokens { get; set; }

    /// <summary>
    /// The maximum number of tokens that can be generated in the chat completion. (Deprecated in favor of max_completion_tokens)
    /// </summary>
    [JsonPropertyName("max_tokens")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    [Obsolete("Use MaxCompletionTokens instead. This property is deprecated and not compatible with o-series models.")]
    public int? MaxTokens { get; set; }

    /// <summary>
    /// Set of 16 key-value pairs that can be attached to an object. This can be useful for storing additional
    /// information about the object in a structured format, and querying for objects via API or the dashboard.
    /// Keys are strings with a maximum length of 64 characters. Values are strings with a maximum length of 512 characters.
    /// </summary>
    [JsonPropertyName("metadata")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public Dictionary<string, string>? Metadata { get; set; }

    /// <summary>
    /// Types of content modalities the model can output. Can include "text" and/or "audio".
    /// </summary>
    [JsonPropertyName("modalities")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public IList<string>? Modalities { get; set; }

    /// <summary>
    /// How many chat completion choices to generate for each input message.
    /// </summary>
    [JsonPropertyName("n")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public int? N { get; set; }

    /// <summary>
    /// Whether to enable parallel function calling during tool use.
    /// </summary>
    [JsonPropertyName("parallel_tool_calls")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public bool? ParallelToolCalls { get; set; }

    /// <summary>
    /// Configuration for a Predicted Output, which can greatly improve response times when large parts of the model response are known ahead of time.
    /// </summary>
    [JsonPropertyName("prediction")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public object? Prediction { get; set; }

    /// <summary>
    /// Number between -2.0 and 2.0. Positive values penalize new tokens based on whether they appear in the text so far.
    /// </summary>
    [JsonPropertyName("presence_penalty")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public float? PresencePenalty { get; set; }

    /// <summary>
    /// Used by OpenAI to cache responses for similar requests to optimize your cache hit rates.
    /// </summary>
    [JsonPropertyName("prompt_cache_key")]
    public string? PromptCacheKey { get; init; }

    /// <summary>
    /// The reasoning effort level for o-series models. Can be "low", "medium", or "high".
    /// </summary>
    [JsonPropertyName("reasoning_effort")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public string? ReasoningEffort { get; set; }

    /// <summary>
    /// An object specifying the format that the model must output.
    /// </summary>
    [JsonPropertyName("response_format")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public ResponseFormat? ResponseFormat { get; set; }

    /// <summary>
    /// A stable identifier used to help detect users of your application that may be violating OpenAI's usage policies.
    /// The IDs should be a string that uniquely identifies each user. We recommend hashing their username or email address,
    /// in order to avoid sending us any identifying information.
    /// </summary>
    [JsonPropertyName("safety_identifier")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public string? SafetyIdentifier { get; set; }

    /// <summary>
    /// If specified, the system will make a best effort to sample deterministically.
    /// </summary>
    [JsonPropertyName("seed")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public long? Seed { get; set; }

    /// <summary>
    /// Specifies the processing type used for serving the request.
    /// If set to 'auto', the request will be processed with the service tier configured in the Project settings.
    /// If set to 'default', the request will be processed with standard pricing and performance.
    /// If set to 'flex' or 'priority', the request will be processed with the corresponding service tier.
    /// Defaults to 'auto'.
    /// </summary>
    [JsonPropertyName("service_tier")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public string? ServiceTier { get; set; }

    /// <summary>
    /// Up to 4 sequences where the API will stop generating further tokens.
    /// </summary>
    [JsonPropertyName("stop")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public StopSequences? Stop { get; set; }

    /// <summary>
    /// Whether or not to store the output of this chat completion request for use in model distillation or evals products.
    /// </summary>
    [JsonPropertyName("store")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public bool? Store { get; set; }

    /// <summary>
    /// If set to true, the model response data will be streamed to the client using server-sent events.
    /// </summary>
    [JsonPropertyName("stream")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public bool? Stream { get; set; }

    /// <summary>
    /// Options for streaming response. Only set this when you set stream: true.
    /// </summary>
    [JsonPropertyName("stream_options")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public object? StreamOptions { get; set; }

    /// <summary>
    /// What sampling temperature to use, between 0 and 2. Higher values like 0.8 will make the output more random,
    /// while lower values like 0.2 will make it more focused and deterministic.
    /// We generally recommend altering this or top_p but not both. Defaults to 1.
    /// </summary>
    [JsonPropertyName("temperature")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public float? Temperature { get; set; }

    /// <summary>
    /// Controls which (if any) tool is called by the model.
    /// </summary>
    [JsonPropertyName("tool_choice")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public ToolChoice? ToolChoice { get; set; }

    /// <summary>
    /// A list of tools the model may call. Can include custom tools or function tools.
    /// </summary>
    [JsonPropertyName("tools")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public IList<Tool>? Tools { get; set; }

    /// <summary>
    /// An integer between 0 and 20 specifying the number of most likely tokens to return at each token position.
    /// </summary>
    [JsonPropertyName("top_logprobs")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public int? TopLogprobs { get; set; }

    /// <summary>
    /// An alternative to sampling with temperature, called nucleus sampling, where the model considers the results of
    /// the tokens with top_p probability mass. So 0.1 means only the tokens comprising the top 10% probability mass are considered.
    /// We generally recommend altering this or temperature but not both.
    /// </summary>
    [JsonPropertyName("top_p")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public float? TopP { get; set; }

    /// <summary>
    /// Level of detail in the model's output. Can be "standard" or "verbose".
    /// </summary>
    [JsonPropertyName("verbosity")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public string? Verbosity { get; set; } = "medium";

    /// <summary>
    /// Web search tool configuration for searching the web for relevant results.
    /// </summary>
    [JsonPropertyName("web_search_options")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public object? WebSearchOptions { get; set; }
}
