// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json;
using System.Text.Json.Serialization;
using System.Text.Json.Serialization.Metadata;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.AI.Agents;

namespace HelloHttpApi.Web;

public class AgentClient(HttpClient httpClient, ILogger<AgentClient> logger)
{
    private static readonly JsonSerializerOptions s_jsonOptions = new(JsonSerializerDefaults.Web)
    {
        DefaultIgnoreCondition = JsonIgnoreCondition.WhenWritingNull
    };

    public async IAsyncEnumerable<AgentRunResponseUpdate> SendMessageStreamAsync(
        string agentName,
        string message,
        string sessionId = "default",
        [System.Runtime.CompilerServices.EnumeratorCancellation] CancellationToken cancellationToken = default)
    {
        var requestId = Guid.NewGuid().ToString();
        var request = new ChatClientAgentRunRequest
        {
            Messages = [new ChatMessage(ChatRole.User, message)]
        };

        var content = JsonContent.Create(request, s_jsonOptions.GetTypeInfo<ChatClientAgentRunRequest>(AgentClientJsonContext.Default));

        var requestUri = new Uri($"/invocations/actor/{agentName}/{sessionId}/{requestId}?stream=true", UriKind.Relative);

        var requestMessage = new HttpRequestMessage(HttpMethod.Post, requestUri)
        {
            Content = content
        };

        using var response = await httpClient.SendAsync(requestMessage, HttpCompletionOption.ResponseHeadersRead, cancellationToken);
        response.EnsureSuccessStatusCode();

        using var stream = await response.Content.ReadAsStreamAsync(cancellationToken);
        using var reader = new StreamReader(stream);

        string? line;
        while ((line = await reader.ReadLineAsync(cancellationToken)) != null)
        {
            // If this indicates completion, break the loop
            if (IsCompletionEvent(line))
            {
                yield break;
            }

            if (line.StartsWith("data: ", StringComparison.Ordinal))
            {
                var jsonData = line.Substring(6); // Remove "data: " prefix

                if (TryParseEventData(jsonData, logger, out var responseUpdate))
                {
                    if (responseUpdate != null)
                    {
                        yield return responseUpdate;
                    }
                }
                else
                {
                    logger.LogWarning("Received unrecognized event data: {JsonData}", jsonData);
                }
            }
        }
    }

    public async Task<AgentResponse> SendMessageAsync(
        string agentName,
        string message,
        string sessionId = "default",
        CancellationToken cancellationToken = default)
    {
        var requestId = Guid.NewGuid().ToString();
        var request = new ChatClientAgentRunRequest
        {
            Messages = [new ChatMessage(ChatRole.User, message)]
        };

        var content = JsonContent.Create(request, s_jsonOptions.GetTypeInfo<ChatClientAgentRunRequest>(AgentClientJsonContext.Default));

        var requestUri = new Uri($"/invocations/actor/{agentName}/{sessionId}/{requestId}?stream=false", UriKind.Relative);

        var requestMessage = new HttpRequestMessage(HttpMethod.Post, requestUri)
        {
            Content = content
        };

        using var response = await httpClient.SendAsync(requestMessage, HttpCompletionOption.ResponseHeadersRead, cancellationToken);
        response.EnsureSuccessStatusCode();

        try
        {
            var agentResponse = await response.Content.ReadFromJsonAsync(s_jsonOptions.GetTypeInfo<AgentResponse>(AgentClientJsonContext.Default), cancellationToken);
            return agentResponse ?? new AgentResponse { Content = "No response received", Status = "error" };
        }
        catch (JsonException ex)
        {
            var responseContent = await response.Content.ReadAsStringAsync(cancellationToken);
            logger.LogError(ex, "Failed to parse agent response JSON: {ResponseContent}", responseContent);
            return new AgentResponse { Content = "Failed to parse response", Status = "error" };
        }
    }

    private static bool TryParseEventData(string jsonData, ILogger logger, out AgentRunResponseUpdate? responseUpdate)
    {
        responseUpdate = null;

        try
        {
            var eventData = JsonSerializer.Deserialize(jsonData, s_jsonOptions.GetTypeInfo<EventData>(AgentClientJsonContext.Default));
            if (eventData?.Event != null)
            {
                var eventElement = eventData.Event.Value;

                // Try to deserialize as AgentRunResponseUpdate for intermediate updates
                try
                {
                    var update = JsonSerializer.Deserialize<AgentRunResponseUpdate>(eventElement.GetRawText(), s_jsonOptions);
                    if (update != null)
                    {
                        responseUpdate = update;
                        return true;
                    }
                }
                catch (JsonException)
                {
                    // If it fails to deserialize as AgentRunResponseUpdate, it might be something else
                    logger.LogDebug("Failed to deserialize event as AgentRunResponseUpdate, might be final response or other data");
                }

                // Fallback: create a simple update with the raw content
                responseUpdate = new AgentRunResponseUpdate(ChatRole.Assistant, eventElement.ToString());
                return true;
            }
        }
        catch (JsonException ex)
        {
            logger.LogError(ex, "Failed to parse event data JSON: {JsonData}", jsonData);
        }

        return false;
    }

    private static bool IsCompletionEvent(string line) => string.Equals("data: completed", line, StringComparison.Ordinal);
}

public class ChatClientAgentRunRequest
{
    [JsonPropertyName("messages")]
    public List<ChatMessage> Messages { get; set; } = [];
}

public class EventData
{
    [JsonPropertyName("event")]
    public JsonElement? Event { get; set; }
}

public class AgentResponse
{
    [JsonPropertyName("content")]
    public string Content { get; set; } = "";

    [JsonPropertyName("status")]
    public string Status { get; set; } = "";
}

/// <summary>
/// Provides extension methods for JSON serialization with source generation support.
/// </summary>
internal static class JsonSerializerExtensions
{
    /// <summary>
    /// Gets the JsonTypeInfo for a type, preferring the one from options if available,
    /// otherwise falling back to the source-generated context.
    /// </summary>
    /// <typeparam name="T">The type to get JsonTypeInfo for.</typeparam>
    /// <param name="options">The JsonSerializerOptions to check first.</param>
    /// <param name="fallbackContext">The fallback JsonSerializerContext to use if not found in options.</param>
    /// <returns>The JsonTypeInfo for the requested type.</returns>
    public static JsonTypeInfo<T> GetTypeInfo<T>(this JsonSerializerOptions options, JsonSerializerContext fallbackContext)
    {
        // Try to get from the options first (if a context is configured)
        if (options.TypeInfoResolver?.GetTypeInfo(typeof(T), options) is JsonTypeInfo<T> typeInfo)
        {
            return typeInfo;
        }

        // Fall back to the provided source-generated context
        return (JsonTypeInfo<T>)fallbackContext.GetTypeInfo(typeof(T))!;
    }
}

/// <summary>
/// Source-generated JSON type information for use by AgentClient.
/// </summary>
[JsonSourceGenerationOptions(
    JsonSerializerDefaults.Web,
    UseStringEnumConverter = true,
    DefaultIgnoreCondition = JsonIgnoreCondition.WhenWritingNull,
    WriteIndented = false)]
[JsonSerializable(typeof(ChatClientAgentRunRequest))]
[JsonSerializable(typeof(ChatMessage))]
[JsonSerializable(typeof(List<ChatMessage>))]
[JsonSerializable(typeof(EventData))]
[JsonSerializable(typeof(AgentRunResponseUpdate))]
[JsonSerializable(typeof(AgentResponse))]
[JsonSerializable(typeof(JsonElement))]
internal sealed partial class AgentClientJsonContext : JsonSerializerContext;
