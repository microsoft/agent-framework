// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Diagnostics.CodeAnalysis;
using System.Text.Json;
using System.Text.Json.Serialization;
using Microsoft.Agents.AI.Hosting.OpenAI.Responses.Converters;

namespace Microsoft.Agents.AI.Hosting.OpenAI.Responses.Models;

/// <summary>
/// The status of a response generation.
/// </summary>
[JsonConverter(typeof(SnakeCaseEnumConverter<ResponseStatus>))]
internal enum ResponseStatus
{
    /// <summary>
    /// The response has been completed.
    /// </summary>
    Completed,

    /// <summary>
    /// The response generation has failed.
    /// </summary>
    Failed,

    /// <summary>
    /// The response generation is in progress.
    /// </summary>
    InProgress,

    /// <summary>
    /// The response generation has been cancelled.
    /// </summary>
    Cancelled,

    /// <summary>
    /// The response is queued for processing.
    /// </summary>
    Queued,

    /// <summary>
    /// The response is incomplete.
    /// </summary>
    Incomplete
}

/// <summary>
/// Response from creating a model response.
/// </summary>
internal sealed record Response
{
    /// <summary>
    /// The unique identifier for the response.
    /// </summary>
    [JsonPropertyName("id")]
    public required string Id { get; init; }

    /// <summary>
    /// The object type, always "response".
    /// </summary>
    [JsonPropertyName("object")]
    [SuppressMessage("Naming", "CA1720:Identifiers should not match keywords", Justification = "Matches API specification")]
    public string Object => "response";

    /// <summary>
    /// The Unix timestamp (in seconds) for when the response was created.
    /// </summary>
    [JsonPropertyName("created_at")]
    public required long CreatedAt { get; init; }

    /// <summary>
    /// The model used to generate the response.
    /// </summary>
    [JsonPropertyName("model")]
    public string? Model { get; init; }

    /// <summary>
    /// The status of the response generation.
    /// </summary>
    [JsonPropertyName("status")]
    public required ResponseStatus Status { get; init; }

    /// <summary>
    /// The agent used for this response.
    /// </summary>
    [JsonPropertyName("agent")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public AgentId? Agent { get; init; }

    /// <summary>
    /// Gets a value indicating whether the response is in a terminal state (completed, failed, cancelled, or incomplete).
    /// </summary>
    [JsonIgnore]
    public bool IsTerminal => this.Status is ResponseStatus.Completed or ResponseStatus.Failed or ResponseStatus.Cancelled or ResponseStatus.Incomplete;

    /// <summary>
    /// An error object returned when the model fails to generate a response.
    /// </summary>
    [JsonPropertyName("error")]
    [JsonIgnore(Condition = JsonIgnoreCondition.Never)]
    public ResponseError? Error { get; init; }

    /// <summary>
    /// Details about why the response is incomplete.
    /// </summary>
    [JsonPropertyName("incomplete_details")]
    public IncompleteDetails? IncompleteDetails { get; init; }

    /// <summary>
    /// The output items (messages) generated in the response.
    /// </summary>
    [JsonPropertyName("output")]
    public required List<ItemResource> Output { get; init; }

    /// <summary>
    /// A system (or developer) message inserted into the model's context.
    /// </summary>
    [JsonPropertyName("instructions")]
    public string? Instructions { get; init; }

    /// <summary>
    /// Usage statistics for the response.
    /// </summary>
    [JsonPropertyName("usage")]
    public required ResponseUsage Usage { get; init; }

    /// <summary>
    /// Whether to allow the model to run tool calls in parallel.
    /// </summary>
    [JsonPropertyName("parallel_tool_calls")]
    public bool ParallelToolCalls { get; init; } = true;

    /// <summary>
    /// An array of tools the model may call while generating a response.
    /// </summary>
    [JsonPropertyName("tools")]
    public required List<JsonElement> Tools { get; init; }

    /// <summary>
    /// How the model should select which tool (or tools) to use when generating a response.
    /// </summary>
    [JsonPropertyName("tool_choice")]
    public JsonElement? ToolChoice { get; init; }

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
    /// Set of up to 16 key-value pairs that can be attached to a response.
    /// </summary>
    [JsonPropertyName("metadata")]
    public Dictionary<string, string>? Metadata { get; init; }

    /// <summary>
    /// The conversation associated with this response.
    /// </summary>
    [JsonPropertyName("conversation")]
    public ConversationReference? Conversation { get; init; }

    /// <summary>
    /// An upper bound for the number of tokens that can be generated for a response,
    /// including visible output tokens and reasoning tokens.
    /// </summary>
    [JsonPropertyName("max_output_tokens")]
    public int? MaxOutputTokens { get; init; }

    /// <summary>
    /// The unique ID of the previous response to the model.
    /// </summary>
    [JsonPropertyName("previous_response_id")]
    public string? PreviousResponseId { get; init; }

    /// <summary>
    /// Configuration options for reasoning models.
    /// </summary>
    [JsonPropertyName("reasoning")]
    public ReasoningOptions? Reasoning { get; init; }

    /// <summary>
    /// Whether the generated model response is stored for later retrieval.
    /// </summary>
    [JsonPropertyName("store")]
    public bool? Store { get; init; }

    /// <summary>
    /// Configuration options for a text response from the model. Can be plain text or structured JSON data.
    /// </summary>
    [JsonPropertyName("text")]
    public TextConfiguration? Text { get; init; }

    /// <summary>
    /// The truncation strategy used for the model response.
    /// </summary>
    [JsonPropertyName("truncation")]
    public string? Truncation { get; init; }

    /// <summary>
    /// A unique identifier representing the end-user.
    /// </summary>
    [JsonPropertyName("user")]
    public string? User { get; init; }

    /// <summary>
    /// The service tier used for the response.
    /// </summary>
    [JsonPropertyName("service_tier")]
    public string? ServiceTier { get; init; }

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
}

/// <summary>
/// An error object returned when the model fails to generate a response.
/// </summary>
internal sealed record ResponseError
{
    /// <summary>
    /// The error code for the response.
    /// </summary>
    [JsonPropertyName("code")]
    public required string Code { get; init; }

    /// <summary>
    /// A human-readable description of the error.
    /// </summary>
    [JsonPropertyName("message")]
    public required string Message { get; init; }
}

/// <summary>
/// Details about why the response is incomplete.
/// </summary>
internal sealed record IncompleteDetails
{
    /// <summary>
    /// The reason why the response is incomplete. One of "max_output_tokens" or "content_filter".
    /// </summary>
    [JsonPropertyName("reason")]
    public required string Reason { get; init; }
}

/// <summary>
/// Usage statistics for a response.
/// </summary>
internal sealed record ResponseUsage
{
    /// <summary>
    /// Gets a zero usage instance.
    /// </summary>
    public static ResponseUsage Zero { get; } = new()
    {
        InputTokens = 0,
        InputTokensDetails = new InputTokensDetails { CachedTokens = 0 },
        OutputTokens = 0,
        OutputTokensDetails = new OutputTokensDetails { ReasoningTokens = 0 },
        TotalTokens = 0
    };

    /// <summary>
    /// Number of tokens in the input.
    /// </summary>
    [JsonPropertyName("input_tokens")]
    public required int InputTokens { get; init; }

    /// <summary>
    /// A detailed breakdown of the input tokens.
    /// </summary>
    [JsonPropertyName("input_tokens_details")]
    public required InputTokensDetails InputTokensDetails { get; init; }

    /// <summary>
    /// Number of tokens in the output.
    /// </summary>
    [JsonPropertyName("output_tokens")]
    public required int OutputTokens { get; init; }

    /// <summary>
    /// A detailed breakdown of the output tokens.
    /// </summary>
    [JsonPropertyName("output_tokens_details")]
    public required OutputTokensDetails OutputTokensDetails { get; init; }

    /// <summary>
    /// Total number of tokens used.
    /// </summary>
    [JsonPropertyName("total_tokens")]
    public required int TotalTokens { get; init; }

    /// <summary>
    /// Adds two <see cref="ResponseUsage"/> instances together.
    /// </summary>
    /// <param name="left">The first usage instance.</param>
    /// <param name="right">The second usage instance.</param>
    /// <returns>A new <see cref="ResponseUsage"/> instance with the combined values.</returns>
    public static ResponseUsage operator +(ResponseUsage left, ResponseUsage right) =>
        new()
        {
            InputTokens = left.InputTokens + right.InputTokens,
            InputTokensDetails = new InputTokensDetails
            {
                CachedTokens = left.InputTokensDetails.CachedTokens + right.InputTokensDetails.CachedTokens
            },
            OutputTokens = left.OutputTokens + right.OutputTokens,
            OutputTokensDetails = new OutputTokensDetails
            {
                ReasoningTokens = left.OutputTokensDetails.ReasoningTokens + right.OutputTokensDetails.ReasoningTokens
            },
            TotalTokens = left.TotalTokens + right.TotalTokens
        };
}

/// <summary>
/// A detailed breakdown of the input tokens.
/// </summary>
internal sealed record InputTokensDetails
{
    /// <summary>
    /// The number of tokens that were retrieved from the cache.
    /// </summary>
    [JsonPropertyName("cached_tokens")]
    public required int CachedTokens { get; init; }
}

/// <summary>
/// A detailed breakdown of the output tokens.
/// </summary>
internal sealed record OutputTokensDetails
{
    /// <summary>
    /// The number of reasoning tokens.
    /// </summary>
    [JsonPropertyName("reasoning_tokens")]
    public required int ReasoningTokens { get; init; }
}
