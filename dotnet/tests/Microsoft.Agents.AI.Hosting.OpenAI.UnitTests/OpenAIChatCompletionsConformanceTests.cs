// Copyright (c) Microsoft. All rights reserved.

using System.Net.Http;
using System.Text.Json;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Hosting.OpenAI.Tests;

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
}
