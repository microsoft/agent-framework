// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Linq;
using System.Net.Http;
using System.Text.Json;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Hosting.OpenAI.Tests;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Hosting.OpenAI.UnitTests;

/// <summary>
/// Conformance tests for OpenAI Chat Completions API implementation behavior.
/// Tests use real API traces to ensure our implementation produces responses
/// that match OpenAI's wire format when processing actual requests through the server.
/// </summary>
public sealed class OpenAIChatCompletionsConformanceTests : ConformanceTestBase
{
    [Fact]
    public async Task BasicRequestResponseAsync()
    {
        // Arrange
        string requestJson = LoadChatCompletionsTraceFile("basic/request.json");
        using var expectedResponseDoc = LoadChatCompletionsTraceDocument("basic/response.json");
        var expectedResponse = expectedResponseDoc.RootElement;

        // Get the expected response text from the trace to use as mock response
        string expectedText = expectedResponse.GetProperty("choices")[0]
            .GetProperty("message")
            .GetProperty("content").GetString()!;

        HttpClient client = await this.CreateTestServerAsync("basic-agent", "You are a helpful assistant.", expectedText);

        // Act
        HttpResponseMessage httpResponse = await this.SendChatCompletionRequestAsync(client, "basic-agent", requestJson);
        using var responseDoc = await ParseResponseAsync(httpResponse);
        var response = responseDoc.RootElement;

        // Parse the request to verify it was sent correctly
        using var requestDoc = JsonDocument.Parse(requestJson);
        var request = requestDoc.RootElement;

        // Assert - Verify request was properly formatted (structure check)
        AssertJsonPropertyEquals(request, "model", "gpt-4o-mini");
        AssertJsonPropertyExists(request, "messages");
        AssertJsonPropertyEquals(request, "max_completion_tokens", 100);
        AssertJsonPropertyEquals(request, "temperature", 1.0f);
        AssertJsonPropertyEquals(request, "top_p", 1.0f);

        var messages = request.GetProperty("messages");
        Assert.Equal(JsonValueKind.Array, messages.ValueKind);
        Assert.True(messages.GetArrayLength() > 0, "Messages array should not be empty");

        var firstMessage = messages[0];
        AssertJsonPropertyEquals(firstMessage, "role", "user");
        AssertJsonPropertyEquals(firstMessage, "content", "Hello, how are you?");

        // Assert - Response metadata (IDs and timestamps are dynamic, just verify structure)
        AssertJsonPropertyExists(response, "id");
        AssertJsonPropertyEquals(response, "object", "chat.completion");
        AssertJsonPropertyExists(response, "created");
        AssertJsonPropertyExists(response, "model");

        var id = response.GetProperty("id").GetString();
        Assert.NotNull(id);
        Assert.StartsWith("chatcmpl-", id);

        var createdAt = response.GetProperty("created").GetInt64();
        Assert.True(createdAt > 0, "created should be a positive unix timestamp");

        var model = response.GetProperty("model").GetString();
        Assert.NotNull(model);
        Assert.StartsWith("gpt-4o-mini", model);

        // Assert - Choices array structure
        AssertJsonPropertyExists(response, "choices");
        var choices = response.GetProperty("choices");
        Assert.Equal(JsonValueKind.Array, choices.ValueKind);
        Assert.True(choices.GetArrayLength() > 0, "Choices array should not be empty");

        // Assert - Choice structure
        var firstChoice = choices[0];
        AssertJsonPropertyExists(firstChoice, "index");
        AssertJsonPropertyEquals(firstChoice, "index", 0);
        AssertJsonPropertyExists(firstChoice, "message");
        AssertJsonPropertyExists(firstChoice, "finish_reason");

        var finishReason = firstChoice.GetProperty("finish_reason").GetString();
        Assert.NotNull(finishReason);
        Assert.Contains(finishReason, collection: ["stop", "length", "content_filter", "tool_calls"]);

        // Assert - Message structure
        var message = firstChoice.GetProperty("message");
        AssertJsonPropertyExists(message, "role");
        AssertJsonPropertyEquals(message, "role", "assistant");
        AssertJsonPropertyExists(message, "content");

        var content = message.GetProperty("content").GetString();
        Assert.NotNull(content);
        Assert.Equal(expectedText, content); // Verify actual content matches expected

        // Assert - Usage statistics
        AssertJsonPropertyExists(response, "usage");
        var usage = response.GetProperty("usage");
        AssertJsonPropertyExists(usage, "prompt_tokens");
        AssertJsonPropertyExists(usage, "completion_tokens");
        AssertJsonPropertyExists(usage, "total_tokens");

        var promptTokens = usage.GetProperty("prompt_tokens").GetInt32();
        var completionTokens = usage.GetProperty("completion_tokens").GetInt32();
        var totalTokens = usage.GetProperty("total_tokens").GetInt32();

        Assert.True(promptTokens > 0, "prompt_tokens should be positive");
        Assert.True(completionTokens > 0, "completion_tokens should be positive");
        Assert.Equal(promptTokens + completionTokens, totalTokens);

        // Assert - Usage details
        AssertJsonPropertyExists(usage, "prompt_tokens_details");
        var promptDetails = usage.GetProperty("prompt_tokens_details");
        AssertJsonPropertyExists(promptDetails, "cached_tokens");
        AssertJsonPropertyExists(promptDetails, "audio_tokens");
        Assert.True(promptDetails.GetProperty("cached_tokens").GetInt32() >= 0);
        Assert.True(promptDetails.GetProperty("audio_tokens").GetInt32() >= 0);

        AssertJsonPropertyExists(usage, "completion_tokens_details");
        var completionDetails = usage.GetProperty("completion_tokens_details");
        AssertJsonPropertyExists(completionDetails, "reasoning_tokens");
        AssertJsonPropertyExists(completionDetails, "audio_tokens");
        AssertJsonPropertyExists(completionDetails, "accepted_prediction_tokens");
        AssertJsonPropertyExists(completionDetails, "rejected_prediction_tokens");
        Assert.True(completionDetails.GetProperty("reasoning_tokens").GetInt32() >= 0);
        Assert.True(completionDetails.GetProperty("audio_tokens").GetInt32() >= 0);
        Assert.True(completionDetails.GetProperty("accepted_prediction_tokens").GetInt32() >= 0);
        Assert.True(completionDetails.GetProperty("rejected_prediction_tokens").GetInt32() >= 0);

        // Assert - Optional fields
        AssertJsonPropertyExists(response, "service_tier");
        var serviceTier = response.GetProperty("service_tier").GetString();
        Assert.NotNull(serviceTier);
        Assert.True(serviceTier == "default" || serviceTier == "auto", $"service_tier should be 'default' or 'auto', got '{serviceTier}'");
    }

    [Fact]
    public async Task StreamingRequestResponseAsync()
    {
        // Arrange
        string requestJson = LoadChatCompletionsTraceFile("streaming/request.json");
        string expectedResponseSse = LoadChatCompletionsTraceFile("streaming/response.txt");

        // Extract expected text from SSE chunks
        var expectedChunks = ParseChatCompletionChunksFromSse(expectedResponseSse);
        string expectedText = string.Concat(expectedChunks
            .Where(c => c.GetProperty("choices")[0].GetProperty("delta").TryGetProperty("content", out var content))
            .Select(c => c.GetProperty("choices")[0].GetProperty("delta").GetProperty("content").GetString()));

        HttpClient client = await this.CreateTestServerAsync("streaming-agent", "You are a helpful assistant.", expectedText);

        // Act
        HttpResponseMessage httpResponse = await this.SendChatCompletionRequestAsync(client, "streaming-agent", requestJson);

        // Assert - Response should be SSE format
        Assert.Equal("text/event-stream", httpResponse.Content.Headers.ContentType?.MediaType);

        string responseSse = await httpResponse.Content.ReadAsStringAsync();
        var chunks = ParseChatCompletionChunksFromSse(responseSse);

        // Parse the request
        using var requestDoc = JsonDocument.Parse(requestJson);
        var request = requestDoc.RootElement;

        // Assert - Request has stream flag
        AssertJsonPropertyEquals(request, "stream", true);

        // Assert - Response has valid chunks
        Assert.NotEmpty(chunks);

        // Assert - All chunks have same ID
        string? firstId = null;
        foreach (var chunk in chunks)
        {
            AssertJsonPropertyExists(chunk, "id");
            AssertJsonPropertyEquals(chunk, "object", "chat.completion.chunk");
            AssertJsonPropertyExists(chunk, "created");
            AssertJsonPropertyExists(chunk, "model");
            AssertJsonPropertyExists(chunk, "choices");

            string chunkId = chunk.GetProperty("id").GetString()!;
            Assert.StartsWith("chatcmpl-", chunkId);

            firstId ??= chunkId;
            Assert.Equal(firstId, chunkId);
        }

        // Assert - First chunk has role
        var firstChunk = chunks[0];
        var firstChoice = firstChunk.GetProperty("choices")[0];
        AssertJsonPropertyExists(firstChoice, "delta");
        var firstDelta = firstChoice.GetProperty("delta");
        if (firstDelta.TryGetProperty("role", out var role))
        {
            Assert.Equal("assistant", role.GetString());
        }

        // Assert - Content chunks have delta content
        var contentChunks = chunks.Where(c =>
            c.GetProperty("choices")[0].GetProperty("delta").TryGetProperty("content", out _)).ToList();
        Assert.NotEmpty(contentChunks);

        // Assert - Last chunk has finish_reason
        var lastChunk = chunks[^1];
        var lastChoice = lastChunk.GetProperty("choices")[0];
        if (lastChoice.TryGetProperty("finish_reason", out var finishReason) && finishReason.ValueKind != JsonValueKind.Null)
        {
            string reason = finishReason.GetString()!;
            Assert.Contains(reason, collection: ["stop", "length", "tool_calls", "content_filter"]);
        }

        // Assert - Last chunk may have usage
        if (lastChunk.TryGetProperty("usage", out var usage))
        {
            AssertJsonPropertyExists(usage, "prompt_tokens");
            AssertJsonPropertyExists(usage, "completion_tokens");
            AssertJsonPropertyExists(usage, "total_tokens");
        }

        // Assert - Accumulated content matches expected
        string accumulatedText = string.Concat(contentChunks
            .Select(c => c.GetProperty("choices")[0].GetProperty("delta").GetProperty("content").GetString()));
        Assert.NotEmpty(accumulatedText);
    }

    [Fact]
    public async Task FunctionCallingRequestResponseAsync()
    {
        // Arrange
        string requestJson = LoadChatCompletionsTraceFile("function_calling/request.json");
        using var expectedResponseDoc = LoadChatCompletionsTraceDocument("function_calling/response.json");
        var expectedResponse = expectedResponseDoc.RootElement;

        // Get expected function call details
        const string FunctionName = "get_weather";

        HttpClient client = await this.CreateTestServerAsync("function-agent", "You are a helpful assistant.", FunctionName,
            (msg) => [new FunctionCallContent("call_abc123xyz", "get_weather", new Dictionary<string, object?>() {
                { "location", "San Francisco, CA"  },
                { "unit", "fahrenheit" }
            })]
        );

        // Act
        HttpResponseMessage httpResponse = await this.SendChatCompletionRequestAsync(client, "function-agent", requestJson);
        using var responseDoc = await ParseResponseAsync(httpResponse);
        var response = responseDoc.RootElement;

        // Parse the request
        using var requestDoc = JsonDocument.Parse(requestJson);
        var request = requestDoc.RootElement;

        // Assert - Request has tools array
        AssertJsonPropertyExists(request, "tools");
        var tools = request.GetProperty("tools");
        Assert.Equal(JsonValueKind.Array, tools.ValueKind);
        Assert.True(tools.GetArrayLength() > 0);

        // Assert - Tool structure
        var tool = tools[0];
        AssertJsonPropertyEquals(tool, "type", "function");
        AssertJsonPropertyExists(tool, "function");
        var function = tool.GetProperty("function");
        AssertJsonPropertyEquals(function, "name", "get_weather");
        AssertJsonPropertyExists(function, "description");
        AssertJsonPropertyExists(function, "parameters");

        // Assert - Parameters have JSON Schema
        var parameters = function.GetProperty("parameters");
        AssertJsonPropertyEquals(parameters, "type", "object");
        AssertJsonPropertyExists(parameters, "properties");
        AssertJsonPropertyExists(parameters, "required");

        // Assert - Response has tool_calls. Not always will return that, so can default to "stop"
        var choices = response.GetProperty("choices");
        var choice = choices[0];
        var message = choice.GetProperty("message");
        AssertJsonPropertyEquals(choice, "finish_reason", ["tool_calls", "stop"]);
        AssertJsonPropertyExists(message, "tool_calls");

        // Assert - Tool call structure
        var toolCalls = message.GetProperty("tool_calls");
        Assert.Equal(JsonValueKind.Array, toolCalls.ValueKind);
        Assert.True(toolCalls.GetArrayLength() > 0);

        var toolCall = toolCalls[0];
        AssertJsonPropertyExists(toolCall, "id");
        AssertJsonPropertyEquals(toolCall, "type", "function");
        AssertJsonPropertyExists(toolCall, "function");

        var callFunction = toolCall.GetProperty("function");
        AssertJsonPropertyEquals(callFunction, "name", "get_weather");
        AssertJsonPropertyExists(callFunction, "arguments");

        // Assert - Arguments are valid JSON
        string arguments = callFunction.GetProperty("arguments").GetString()!;
        using var argsDoc = JsonDocument.Parse(arguments);
        var argsRoot = argsDoc.RootElement;
        AssertJsonPropertyExists(argsRoot, "location");

        // Assert - Message content is null when tool_calls present. Can be absent or null.
        if (message.TryGetProperty("content", out var contentProp))
        {
            Assert.Equal(JsonValueKind.Null, contentProp.ValueKind);
        }
    }

    [Fact]
    public async Task SystemMessageRequestResponseAsync()
    {
        // Arrange
        string requestJson = LoadChatCompletionsTraceFile("system_message/request.json");
        using var expectedResponseDoc = LoadChatCompletionsTraceDocument("system_message/response.json");
        var expectedResponse = expectedResponseDoc.RootElement;

        string expectedText = expectedResponse.GetProperty("choices")[0]
                   .GetProperty("message")
         .GetProperty("content").GetString()!;

        HttpClient client = await this.CreateTestServerAsync("system-agent", "You are a helpful assistant that speaks like a pirate.", expectedText);

        // Act
        HttpResponseMessage httpResponse = await this.SendChatCompletionRequestAsync(client, "system-agent", requestJson);
        using var responseDoc = await ParseResponseAsync(httpResponse);
        var response = responseDoc.RootElement;

        // Parse the request
        using var requestDoc = JsonDocument.Parse(requestJson);
        var request = requestDoc.RootElement;

        // Assert - Request has messages with system role
        var messages = request.GetProperty("messages");
        Assert.True(messages.GetArrayLength() >= 2);

        var systemMessage = messages[0];
        AssertJsonPropertyEquals(systemMessage, "role", "system");
        AssertJsonPropertyExists(systemMessage, "content");
        string systemContent = systemMessage.GetProperty("content").GetString()!;
        Assert.Contains("pirate", systemContent, System.StringComparison.OrdinalIgnoreCase);

        var userMessage = messages[1];
        AssertJsonPropertyEquals(userMessage, "role", "user");

        // Assert - Response reflects system message influence
        var responseMessage = response.GetProperty("choices")[0].GetProperty("message");
        string content = responseMessage.GetProperty("content").GetString()!;
        Assert.NotNull(content);
        Assert.Equal(expectedText, content);
    }

    [Fact]
    public async Task MultiTurnConversationRequestResponseAsync()
    {
        // Arrange
        string requestJson = LoadChatCompletionsTraceFile("multi_turn/request.json");
        using var expectedResponseDoc = LoadChatCompletionsTraceDocument("multi_turn/response.json");
        var expectedResponse = expectedResponseDoc.RootElement;

        string expectedText = expectedResponse.GetProperty("choices")[0]
            .GetProperty("message")
            .GetProperty("content").GetString()!;

        HttpClient client = await this.CreateTestServerAsync("multi-turn-agent", "You are a helpful assistant.", expectedText);

        // Act
        HttpResponseMessage httpResponse = await this.SendChatCompletionRequestAsync(client, "multi-turn-agent", requestJson);
        using var responseDoc = await ParseResponseAsync(httpResponse);
        var response = responseDoc.RootElement;

        // Parse the request
        using var requestDoc = JsonDocument.Parse(requestJson);
        var request = requestDoc.RootElement;

        // Assert - Request has conversation history
        var messages = request.GetProperty("messages");
        Assert.True(messages.GetArrayLength() >= 3, "Should have at least 3 messages for multi-turn");

        // Assert - Message sequence alternates between user and assistant
        AssertJsonPropertyEquals(messages[0], "role", "user");
        AssertJsonPropertyEquals(messages[1], "role", "assistant");
        AssertJsonPropertyEquals(messages[2], "role", "user");

        // Assert - Response continues conversation
        var responseMessage = response.GetProperty("choices")[0].GetProperty("message");
        AssertJsonPropertyEquals(responseMessage, "role", "assistant");
        string content = responseMessage.GetProperty("content").GetString()!;
        Assert.NotNull(content);
        Assert.Equal(expectedText, content);

        // Assert - Usage tokens account for conversation history
        var usage = response.GetProperty("usage");
        int promptTokens = usage.GetProperty("prompt_tokens").GetInt32();
        Assert.True(promptTokens > 20, "Prompt tokens should account for conversation history");
    }

    [Fact]
    public async Task JsonModeRequestResponseAsync()
    {
        // Arrange
        string requestJson = LoadChatCompletionsTraceFile("json_mode/request.json");
        using var expectedResponseDoc = LoadChatCompletionsTraceDocument("json_mode/response.json");
        var expectedResponse = expectedResponseDoc.RootElement;

        string expectedText = expectedResponse.GetProperty("choices")[0]
       .GetProperty("message")
    .GetProperty("content").GetString()!;

        HttpClient client = await this.CreateTestServerAsync("json-agent", "You are a helpful assistant that outputs JSON.", expectedText);

        // Act
        HttpResponseMessage httpResponse = await this.SendChatCompletionRequestAsync(client, "json-agent", requestJson);
        using var responseDoc = await ParseResponseAsync(httpResponse);
        var response = responseDoc.RootElement;

        // Parse the request
        using var requestDoc = JsonDocument.Parse(requestJson);
        var request = requestDoc.RootElement;

        // Assert - Request has response_format with json_schema
        AssertJsonPropertyExists(request, "response_format");
        var responseFormat = request.GetProperty("response_format");
        AssertJsonPropertyEquals(responseFormat, "type", "json_schema");
        AssertJsonPropertyExists(responseFormat, "json_schema");

        var jsonSchema = responseFormat.GetProperty("json_schema");
        AssertJsonPropertyEquals(jsonSchema, "name", "person_info");
        AssertJsonPropertyEquals(jsonSchema, "strict", true);
        AssertJsonPropertyExists(jsonSchema, "schema");

        var schema = jsonSchema.GetProperty("schema");
        AssertJsonPropertyEquals(schema, "type", "object");
        AssertJsonPropertyExists(schema, "properties");
        AssertJsonPropertyExists(schema, "required");

        // Assert - Response content is valid JSON matching schema
        var responseMessage = response.GetProperty("choices")[0].GetProperty("message");
        string content = responseMessage.GetProperty("content").GetString()!;
        Assert.NotNull(content);
        Assert.Equal(expectedText, content);

        using var jsonDoc = JsonDocument.Parse(content);
        var jsonRoot = jsonDoc.RootElement;
        AssertJsonPropertyExists(jsonRoot, "name");
        AssertJsonPropertyExists(jsonRoot, "age");
        AssertJsonPropertyExists(jsonRoot, "occupation");

        Assert.Equal(JsonValueKind.String, jsonRoot.GetProperty("name").ValueKind);
        Assert.Equal(JsonValueKind.Number, jsonRoot.GetProperty("age").ValueKind);
        Assert.Equal(JsonValueKind.String, jsonRoot.GetProperty("occupation").ValueKind);
    }

    [Fact]
    public async Task ToolsSerializationDeserializationAsync()
    {
        // Arrange
        string requestJson = LoadChatCompletionsTraceFile("tools/request.json");
        using var expectedResponseDoc = LoadChatCompletionsTraceDocument("tools/response.json");

        HttpClient client = await this.CreateTestServerAsync(
            "tools-agent",
            "You are a helpful assistant with access to weather and time tools.",
            "tool-call",
            (msg) => [new FunctionCallContent("call_abc123", "get_weather", new Dictionary<string, object?>() {
                { "location", "San Francisco, CA" },
                { "unit", "fahrenheit" }
            })]
        );

        // Act
        HttpResponseMessage httpResponse = await this.SendChatCompletionRequestAsync(client, "tools-agent", requestJson);
        using var responseDoc = await ParseResponseAsync(httpResponse);
        var response = responseDoc.RootElement;

        // Parse the request
        using var requestDoc = JsonDocument.Parse(requestJson);
        var request = requestDoc.RootElement;

        // Assert - Request has tools array with proper structure
        AssertJsonPropertyExists(request, "tools");
        var tools = request.GetProperty("tools");
        Assert.Equal(JsonValueKind.Array, tools.ValueKind);
        Assert.Equal(2, tools.GetArrayLength());

        // Assert - First tool (get_weather)
        var weatherTool = tools[0];
        AssertJsonPropertyEquals(weatherTool, "type", "function");
        AssertJsonPropertyExists(weatherTool, "function");

        var weatherFunction = weatherTool.GetProperty("function");
        AssertJsonPropertyEquals(weatherFunction, "name", "get_weather");
        AssertJsonPropertyExists(weatherFunction, "description");
        AssertJsonPropertyExists(weatherFunction, "parameters");

        var weatherParams = weatherFunction.GetProperty("parameters");
        AssertJsonPropertyEquals(weatherParams, "type", "object");
        AssertJsonPropertyExists(weatherParams, "properties");
        AssertJsonPropertyExists(weatherParams, "required");

        // Verify location property exists
        var properties = weatherParams.GetProperty("properties");
        AssertJsonPropertyExists(properties, "location");
        AssertJsonPropertyExists(properties, "unit");

        // Assert - Second tool (get_time)
        var timeTool = tools[1];
        AssertJsonPropertyEquals(timeTool, "type", "function");

        var timeFunction = timeTool.GetProperty("function");
        AssertJsonPropertyEquals(timeFunction, "name", "get_time");
        AssertJsonPropertyExists(timeFunction, "description");
        AssertJsonPropertyExists(timeFunction, "parameters");

        // Assert - Response structure
        AssertJsonPropertyExists(response, "id");
        AssertJsonPropertyEquals(response, "object", "chat.completion");
        AssertJsonPropertyExists(response, "created");
        AssertJsonPropertyExists(response, "model");

        // Assert - Response has tool_calls in choices
        var choices = response.GetProperty("choices");
        Assert.Equal(JsonValueKind.Array, choices.ValueKind);
        Assert.True(choices.GetArrayLength() > 0);

        var choice = choices[0];
        AssertJsonPropertyExists(choice, "finish_reason");
        AssertJsonPropertyEquals(choice, "finish_reason", anyOfValues: ["tool_calls", "stop"]);
        AssertJsonPropertyExists(choice, "message");

        var message = choice.GetProperty("message");
        AssertJsonPropertyEquals(message, "role", "assistant");
        AssertJsonPropertyExists(message, "tool_calls");

        // Assert - Tool calls array structure
        var toolCalls = message.GetProperty("tool_calls");
        Assert.Equal(JsonValueKind.Array, toolCalls.ValueKind);
        Assert.True(toolCalls.GetArrayLength() > 0);

        var toolCall = toolCalls[0];
        AssertJsonPropertyExists(toolCall, "id");
        AssertJsonPropertyEquals(toolCall, "type", "function");
        AssertJsonPropertyExists(toolCall, "function");

        var callFunction = toolCall.GetProperty("function");
        AssertJsonPropertyEquals(callFunction, "name", "get_weather");
        AssertJsonPropertyExists(callFunction, "arguments");

        // Assert - Tool call arguments are valid JSON
        string arguments = callFunction.GetProperty("arguments").GetString()!;
        using var argsDoc = JsonDocument.Parse(arguments);
        var argsRoot = argsDoc.RootElement;
        AssertJsonPropertyExists(argsRoot, "location");
        AssertJsonPropertyEquals(argsRoot, "location", "San Francisco, CA");
        AssertJsonPropertyEquals(argsRoot, "unit", "fahrenheit");

        // Assert - Message content is null when tool_calls present
        if (message.TryGetProperty("content", out var contentProp))
        {
            Assert.Equal(JsonValueKind.Null, contentProp.ValueKind);
        }

        // Assert - Usage statistics
        AssertJsonPropertyExists(response, "usage");
        var usage = response.GetProperty("usage");
        AssertJsonPropertyExists(usage, "prompt_tokens");
        AssertJsonPropertyExists(usage, "completion_tokens");
        AssertJsonPropertyExists(usage, "total_tokens");

        var promptTokens = usage.GetProperty("prompt_tokens").GetInt32();
        var completionTokens = usage.GetProperty("completion_tokens").GetInt32();
        var totalTokens = usage.GetProperty("total_tokens").GetInt32();

        Assert.True(promptTokens > 0);
        Assert.True(completionTokens > 0);
        Assert.Equal(promptTokens + completionTokens, totalTokens);

        // Assert - Service tier
        AssertJsonPropertyExists(response, "service_tier");
        var serviceTier = response.GetProperty("service_tier").GetString();
        Assert.NotNull(serviceTier);
    }

    /// <summary>
    /// Helper to parse chat completion chunks from SSE response.
    /// </summary>
    private static List<JsonElement> ParseChatCompletionChunksFromSse(string sseContent)
    {
        var chunks = new List<JsonElement>();
        var lines = sseContent.Split('\n');

        for (int i = 0; i < lines.Length; i++)
        {
            var line = lines[i].TrimEnd('\r');

            if (line.StartsWith("data: ", System.StringComparison.Ordinal))
            {
                var jsonData = line.Substring("data: ".Length);

                // Skip [DONE] marker
                if (jsonData == "[DONE]")
                {
                    continue;
                }

                try
                {
                    var doc = JsonDocument.Parse(jsonData);
                    chunks.Add(doc.RootElement.Clone());
                }
                catch
                {
                    // Skip invalid JSON
                }
            }
        }

        return chunks;
    }
}
