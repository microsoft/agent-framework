// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json;
using System.Text.Json.Serialization;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.AI.Agents;

namespace HelloHttpApi.Web;

public class AgentClient(HttpClient httpClient, ILogger<AgentClient> logger)
{
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

        var content = JsonContent.Create(request, AgentClientJsonContext.Default.ChatClientAgentRunRequest);

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

        var content = JsonContent.Create(request, AgentClientJsonContext.Default.ChatClientAgentRunRequest);

        var requestUri = new Uri($"/invocations/actor/{agentName}/{sessionId}/{requestId}?stream=false", UriKind.Relative);

        var requestMessage = new HttpRequestMessage(HttpMethod.Post, requestUri)
        {
            Content = content
        };

        using var response = await httpClient.SendAsync(requestMessage, HttpCompletionOption.ResponseHeadersRead, cancellationToken);
        response.EnsureSuccessStatusCode();

        try
        {
            var agentResponse = await response.Content.ReadFromJsonAsync(AgentClientJsonContext.Default.AgentResponse, cancellationToken);
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
            var eventData = JsonSerializer.Deserialize(jsonData, AgentClientJsonContext.Default.EventData);
            if (eventData?.Event != null)
            {
                var eventElement = eventData.Event.Value;

                // Try to deserialize as AgentRunResponseUpdate for intermediate updates
                try
                {
                    var update = JsonSerializer.Deserialize<AgentRunResponseUpdate>(eventElement.GetRawText(), AgentAbstractionsJsonUtilities.DefaultOptions);
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
/// Source-generated JSON type information for use by AgentClient.
/// </summary>
[JsonSourceGenerationOptions(
    JsonSerializerDefaults.Web,
    UseStringEnumConverter = true,
    DefaultIgnoreCondition = JsonIgnoreCondition.WhenWritingNull,
    WriteIndented = false)]
[JsonSerializable(typeof(ChatClientAgentRunRequest))]
[JsonSerializable(typeof(EventData))]
[JsonSerializable(typeof(AgentResponse))]
internal sealed partial class AgentClientJsonContext : JsonSerializerContext;
