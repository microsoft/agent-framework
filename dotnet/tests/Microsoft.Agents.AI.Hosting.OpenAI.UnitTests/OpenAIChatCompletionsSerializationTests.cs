// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json;
using Microsoft.Agents.AI.Hosting.OpenAI.ChatCompletions.Models;
using Microsoft.Agents.AI.Hosting.OpenAI.Tests;

namespace Microsoft.Agents.AI.Hosting.OpenAI.UnitTests;

/// <summary>
/// Tests for OpenAI ChatCompletions API model serialization and deserialization.
/// These tests verify that our models correctly serialize to and deserialize from JSON
/// matching the OpenAI wire format, without testing actual API implementation behavior.
/// </summary>
public sealed class OpenAIChatCompletionsSerializationTests : ConformanceTestBase
{
    #region Request Deserialization Tests

    [Fact]
    public void Deserialize_BasicRequest_Success()
    {
        // Arrange
        string json = LoadChatCompletionsTraceFile("basic/request.json");

        // Act
        CreateChatCompletion? request = JsonSerializer.Deserialize(json, ChatCompletions.ChatCompletionsJsonContext.Default.CreateChatCompletion);

        // Assert
        Assert.NotNull(request);
        Assert.Equal("gpt-4o-mini", request.Model);
        Assert.NotNull(request.Messages);
        Assert.True(request.Messages.Count > 0);
        Assert.Equal(100, request.MaxCompletionTokens);
    }

    [Fact]
    public void Deserialize_BasicRequest_RoundTrip()
    {
        // Arrange
        string originalJson = LoadChatCompletionsTraceFile("basic/request.json");

        // Act
        CreateChatCompletion? request = JsonSerializer.Deserialize(originalJson, ChatCompletions.ChatCompletionsJsonContext.Default.CreateChatCompletion);
        string reserializedJson = JsonSerializer.Serialize(request, ChatCompletions.ChatCompletionsJsonContext.Default.CreateChatCompletion);
        CreateChatCompletion? roundtripped = JsonSerializer.Deserialize(reserializedJson, ChatCompletions.ChatCompletionsJsonContext.Default.CreateChatCompletion);

        // Assert
        Assert.NotNull(request);
        Assert.NotNull(roundtripped);
        Assert.Equal(request.Model, roundtripped.Model);
        Assert.Equal(request.MaxCompletionTokens, roundtripped.MaxCompletionTokens);
        Assert.Equal(request.Messages.Count, roundtripped.Messages.Count);
    }

    [Fact]
    public void Deserialize_BasicRequest_HasMessages()
    {
        // Arrange
        string json = LoadChatCompletionsTraceFile("basic/request.json");

        // Act
        CreateChatCompletion? request = JsonSerializer.Deserialize(json, ChatCompletions.ChatCompletionsJsonContext.Default.CreateChatCompletion);

        // Assert
        Assert.NotNull(request);
        Assert.NotNull(request.Messages);
        Assert.Single(request.Messages);

        var message = request.Messages[0];
        Assert.Equal("user", message.Role);
        Assert.NotNull(message.Content);
    }

    [Fact]
    public void Deserialize_StreamingRequest_HasStreamFlag()
    {
        // Arrange
        string json = LoadChatCompletionsTraceFile("streaming/request.json");

        // Act
        CreateChatCompletion? request = JsonSerializer.Deserialize(json, ChatCompletions.ChatCompletionsJsonContext.Default.CreateChatCompletion);

        // Assert
        Assert.NotNull(request);
        Assert.True(request.Stream);
        Assert.Equal(150, request.MaxCompletionTokens);
    }

    [Fact]
    public void Deserialize_SystemMessageRequest_HasSystemRole()
    {
        // Arrange
        string json = LoadChatCompletionsTraceFile("system_message/request.json");

        // Act
        CreateChatCompletion? request = JsonSerializer.Deserialize(json, ChatCompletions.ChatCompletionsJsonContext.Default.CreateChatCompletion);

        // Assert
        Assert.NotNull(request);
        Assert.NotNull(request.Messages);
        Assert.True(request.Messages.Count >= 2);
        Assert.Equal("system", request.Messages[0].Role);
        Assert.Equal("user", request.Messages[1].Role);
    }

    [Fact]
    public void Deserialize_MultiTurnRequest_HasMultipleMessages()
    {
        // Arrange
        string json = LoadChatCompletionsTraceFile("multi_turn/request.json");

        // Act
        CreateChatCompletion? request = JsonSerializer.Deserialize(json, ChatCompletions.ChatCompletionsJsonContext.Default.CreateChatCompletion);

        // Assert
        Assert.NotNull(request);
        Assert.NotNull(request.Messages);
        Assert.True(request.Messages.Count >= 3);
        Assert.Equal("user", request.Messages[0].Role);
        Assert.Equal("assistant", request.Messages[1].Role);
        Assert.Equal("user", request.Messages[2].Role);
    }

    [Fact]
    public void Deserialize_FunctionCallingRequest_HasTools()
    {
        // Arrange
        string json = LoadChatCompletionsTraceFile("function_calling/request.json");

        // Act
        CreateChatCompletion? request = JsonSerializer.Deserialize(json, ChatCompletions.ChatCompletionsJsonContext.Default.CreateChatCompletion);

        // Assert
        Assert.NotNull(request);
        Assert.NotNull(request.Tools);
        Assert.Single(request.Tools);
        Assert.NotNull(request.ToolChoice?.Mode);
        Assert.Equal("auto", request.ToolChoice.Mode);
    }

    [Fact]
    public void Deserialize_JsonModeRequest_HasResponseFormat()
    {
        // Arrange
        string json = LoadChatCompletionsTraceFile("json_mode/request.json");

        // Act
        CreateChatCompletion? request = JsonSerializer.Deserialize(json, ChatCompletions.ChatCompletionsJsonContext.Default.CreateChatCompletion);

        // Assert
        Assert.NotNull(request);
        Assert.NotNull(request.ResponseFormat);
    }

    [Fact]
    public void Deserialize_AllRequests_CanBeDeserialized()
    {
        // Arrange
        string[] requestPaths =
        [
            "basic/request.json",
            "streaming/request.json",
            "system_message/request.json",
            "multi_turn/request.json",
            "function_calling/request.json",
            "json_mode/request.json"
        ];

        foreach (var path in requestPaths)
        {
            string json = LoadChatCompletionsTraceFile(path);

            // Act & Assert - Should not throw
            CreateChatCompletion? request = JsonSerializer.Deserialize(json, ChatCompletions.ChatCompletionsJsonContext.Default.CreateChatCompletion);
            Assert.NotNull(request);
            Assert.NotNull(request.Messages);
            Assert.True(request.Messages.Count > 0, $"Request from {path} should have messages");
        }
    }

    #endregion

    #region Response Deserialization Tests

    [Fact]
    public void Deserialize_BasicResponse_Success()
    {
        // Arrange
        string json = LoadChatCompletionsTraceFile("basic/response.json");

        // Act
        ChatCompletion? response = JsonSerializer.Deserialize(json, ChatCompletions.ChatCompletionsJsonContext.Default.ChatCompletion);

        // Assert
        Assert.NotNull(response);
        Assert.StartsWith("chatcmpl-", response.Id);
        Assert.Equal("chat.completion", response.Object);
        Assert.True(response.Created > 0);
        Assert.NotNull(response.Model);
        Assert.StartsWith("gpt-4o-mini", response.Model);
    }

    [Fact]
    public void Deserialize_BasicResponse_HasChoices()
    {
        // Arrange
        string json = LoadChatCompletionsTraceFile("basic/response.json");

        // Act
        ChatCompletion? response = JsonSerializer.Deserialize(json, ChatCompletions.ChatCompletionsJsonContext.Default.ChatCompletion);

        // Assert
        Assert.NotNull(response);
        Assert.NotNull(response.Choices);
        Assert.Single(response.Choices);

        var choice = response.Choices[0];
        Assert.Equal(0, choice.Index);
        Assert.NotNull(choice.Message);
        Assert.Equal("assistant", choice.Message.Role);
        Assert.NotNull(choice.Message.Content);
        Assert.NotNull(choice.FinishReason);
    }

    [Fact]
    public void Deserialize_BasicResponse_HasUsage()
    {
        // Arrange
        string json = LoadChatCompletionsTraceFile("basic/response.json");

        // Act
        ChatCompletion? response = JsonSerializer.Deserialize(json, ChatCompletions.ChatCompletionsJsonContext.Default.ChatCompletion);

        // Assert
        Assert.NotNull(response);
        Assert.NotNull(response.Usage);
        Assert.True(response.Usage.PromptTokens > 0);
        Assert.True(response.Usage.CompletionTokens > 0);
        Assert.Equal(response.Usage.PromptTokens + response.Usage.CompletionTokens, response.Usage.TotalTokens);
        Assert.NotNull(response.Usage.PromptTokensDetails);
        Assert.NotNull(response.Usage.CompletionTokensDetails);
    }

    [Fact]
    public void Deserialize_SystemMessageResponse_HasContent()
    {
        // Arrange
        string json = LoadChatCompletionsTraceFile("system_message/response.json");

        // Act
        ChatCompletion? response = JsonSerializer.Deserialize(json, ChatCompletions.ChatCompletionsJsonContext.Default.ChatCompletion);

        // Assert
        Assert.NotNull(response);
        Assert.NotNull(response.Choices);
        var message = response.Choices[0].Message;
        Assert.Equal("assistant", message.Role);
        Assert.NotNull(message.Content);
        Assert.Contains("Ahoy, matey", message.Content, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public void Deserialize_MultiTurnResponse_HasContent()
    {
        // Arrange
        string json = LoadChatCompletionsTraceFile("multi_turn/response.json");

        // Act
        ChatCompletion? response = JsonSerializer.Deserialize(json, ChatCompletions.ChatCompletionsJsonContext.Default.ChatCompletion);

        // Assert
        Assert.NotNull(response);
        Assert.NotNull(response.Choices);
        var message = response.Choices[0].Message;
        Assert.Equal("assistant", message.Role);
        Assert.NotNull(message.Content);
    }

    [Fact]
    public void Deserialize_FunctionCallingResponse_HasToolCalls()
    {
        // Arrange
        string json = LoadChatCompletionsTraceFile("function_calling/response.json");

        // Act
        ChatCompletion? response = JsonSerializer.Deserialize(json, ChatCompletions.ChatCompletionsJsonContext.Default.ChatCompletion);

        // Assert
        Assert.NotNull(response);
        Assert.NotNull(response.Choices);

        var choice = response.Choices[0];
        Assert.Equal("tool_calls", choice.FinishReason);

        var message = choice.Message;
        Assert.NotNull(message.ToolCalls);
        Assert.Single(message.ToolCalls);

        var toolCall = message.ToolCalls[0];
        Assert.NotNull(toolCall.Id);
        Assert.StartsWith("call_", toolCall.Id);
        Assert.Equal("function", toolCall.Type);
        Assert.NotNull(toolCall.Function);
        Assert.Equal("get_weather", toolCall.Function.Name);
        Assert.NotNull(toolCall.Function.Arguments);
    }

    [Fact]
    public void Deserialize_JsonModeResponse_HasStructuredOutput()
    {
        // Arrange
        string json = LoadChatCompletionsTraceFile("json_mode/response.json");

        // Act
        ChatCompletion? response = JsonSerializer.Deserialize(json, ChatCompletions.ChatCompletionsJsonContext.Default.ChatCompletion);

        // Assert
        Assert.NotNull(response);
        Assert.NotNull(response.Choices);

        var message = response.Choices[0].Message;
        Assert.NotNull(message.Content);

        // Verify the content is valid JSON
        using var jsonDoc = JsonDocument.Parse(message.Content);
        var jsonRoot = jsonDoc.RootElement;
        Assert.Equal(JsonValueKind.Object, jsonRoot.ValueKind);
        Assert.True(jsonRoot.TryGetProperty("name", out _));
        Assert.True(jsonRoot.TryGetProperty("age", out _));
        Assert.True(jsonRoot.TryGetProperty("occupation", out _));
    }

    [Fact]
    public void Deserialize_AllResponses_HaveRequiredFields()
    {
        // Arrange
        string[] responsePaths =
        [
            "basic/response.json",
            "system_message/response.json",
            "multi_turn/response.json",
            "function_calling/response.json",
            "json_mode/response.json"
        ];

        foreach (var path in responsePaths)
        {
            string json = LoadChatCompletionsTraceFile(path);

            // Act
            ChatCompletion? response = JsonSerializer.Deserialize(json, ChatCompletions.ChatCompletionsJsonContext.Default.ChatCompletion);

            // Assert
            Assert.NotNull(response);
            Assert.NotNull(response.Id);
            Assert.Equal("chat.completion", response.Object);
            Assert.True(response.Created > 0, $"Response from {path} should have created timestamp");
            Assert.NotNull(response.Model);
            Assert.NotNull(response.Choices);
            Assert.True(response.Choices.Count > 0, $"Response from {path} should have choices");
        }
    }

    [Fact]
    public void Deserialize_ResponseRoundTrip_PreservesData()
    {
        // Arrange
        string originalJson = LoadChatCompletionsTraceFile("basic/response.json");

        // Act - Deserialize and re-serialize
        ChatCompletion? response = JsonSerializer.Deserialize(originalJson, ChatCompletions.ChatCompletionsJsonContext.Default.ChatCompletion);
        string reserializedJson = JsonSerializer.Serialize(response, ChatCompletions.ChatCompletionsJsonContext.Default.ChatCompletion);
        ChatCompletion? roundtripped = JsonSerializer.Deserialize(reserializedJson, ChatCompletions.ChatCompletionsJsonContext.Default.ChatCompletion);

        // Assert
        Assert.NotNull(response);
        Assert.NotNull(roundtripped);
        Assert.Equal(response.Id, roundtripped.Id);
        Assert.Equal(response.Created, roundtripped.Created);
        Assert.Equal(response.Model, roundtripped.Model);
        Assert.Equal(response.Choices.Count, roundtripped.Choices.Count);
    }

    #endregion

    #region Streaming Chunk Deserialization Tests

    [Fact]
    public void ParseStreamingChunks_BasicFormat_Success()
    {
        // Arrange
        string sseContent = LoadChatCompletionsTraceFile("streaming/response.txt");

        // Act
        var chunks = ParseChatCompletionChunksFromSse(sseContent);

        // Assert
        Assert.NotEmpty(chunks);
        Assert.All(chunks, chunk =>
        {
            ChatCompletionChunk? parsed = JsonSerializer.Deserialize(chunk.GetRawText(), ChatCompletions.ChatCompletionsJsonContext.Default.ChatCompletionChunk);
            Assert.NotNull(parsed);
            Assert.NotNull(parsed.Id);
            Assert.Equal("chat.completion.chunk", parsed.Object);
            Assert.True(parsed.Created > 0);
            Assert.NotNull(parsed.Model);
            Assert.NotNull(parsed.Choices);
        });
    }

    [Fact]
    public void ParseStreamingChunks_AllChunksSameId()
    {
        // Arrange
        string sseContent = LoadChatCompletionsTraceFile("streaming/response.txt");

        // Act
        var chunks = ParseChatCompletionChunksFromSse(sseContent);

        // Deserialize chunks
        var parsedChunks = chunks
            .Select(c => JsonSerializer.Deserialize(c.GetRawText(), ChatCompletions.ChatCompletionsJsonContext.Default.ChatCompletionChunk))
            .Where(c => c != null)
            .ToList();

        // Assert
        Assert.NotEmpty(parsedChunks);

        string? firstId = parsedChunks[0]!.Id;
        Assert.NotNull(firstId);
        Assert.StartsWith("chatcmpl-", firstId);

        Assert.All(parsedChunks, chunk => Assert.Equal(firstId, chunk!.Id));
    }

    [Fact]
    public void ParseStreamingChunks_FirstChunkHasRole()
    {
        // Arrange
        string sseContent = LoadChatCompletionsTraceFile("streaming/response.txt");

        // Act
        var chunks = ParseChatCompletionChunksFromSse(sseContent);
        var firstChunk = JsonSerializer.Deserialize(chunks[0].GetRawText(), ChatCompletions.ChatCompletionsJsonContext.Default.ChatCompletionChunk);

        // Assert
        Assert.NotNull(firstChunk);
        Assert.NotNull(firstChunk.Choices);
        Assert.True(firstChunk.Choices.Count > 0);

        var firstChoice = firstChunk.Choices[0];
        Assert.NotNull(firstChoice.Delta);

        if (firstChoice.Delta.Role != null)
        {
            Assert.Equal("assistant", firstChoice.Delta.Role);
        }
    }

    [Fact]
    public void ParseStreamingChunks_AccumulateContent_MatchesExpected()
    {
        // Arrange
        string sseContent = LoadChatCompletionsTraceFile("streaming/response.txt");

        // Act
        var chunks = ParseChatCompletionChunksFromSse(sseContent);
        var contentPieces = new List<string>();

        foreach (var chunkJson in chunks)
        {
            var chunk = JsonSerializer.Deserialize(chunkJson.GetRawText(), ChatCompletions.ChatCompletionsJsonContext.Default.ChatCompletionChunk);
            if (chunk?.Choices != null && chunk.Choices.Count > 0)
            {
                var delta = chunk.Choices[0].Delta;
                if (!string.IsNullOrEmpty(delta?.Content))
                {
                    contentPieces.Add(delta.Content);
                }
            }
        }

        // Assert
        Assert.NotEmpty(contentPieces);
        string fullText = string.Concat(contentPieces);
        Assert.NotEmpty(fullText);
        Assert.Contains("circuits", fullText);
        Assert.Contains("flight", fullText);
    }

    [Fact]
    public void ParseStreamingChunks_LastChunkHasFinishReason()
    {
        // Arrange
        string sseContent = LoadChatCompletionsTraceFile("streaming/response.txt");

        // Act
        var chunks = ParseChatCompletionChunksFromSse(sseContent);

        // Find chunks with finish_reason
        var chunksWithFinishReason = new List<ChatCompletionChunk>();
        foreach (var chunkJson in chunks)
        {
            var chunk = JsonSerializer.Deserialize(chunkJson.GetRawText(), ChatCompletions.ChatCompletionsJsonContext.Default.ChatCompletionChunk);
            if (chunk?.Choices != null && chunk.Choices.Count > 0 && !string.IsNullOrEmpty(chunk.Choices[0].FinishReason))
            {
                chunksWithFinishReason.Add(chunk);
            }
        }

        // Assert
        Assert.NotEmpty(chunksWithFinishReason);
        var lastChunk = chunksWithFinishReason.Last();
        Assert.Contains(lastChunk.Choices[0].FinishReason, collection: ["stop", "length", "tool_calls", "content_filter"]);
    }

    [Fact]
    public void ParseStreamingChunks_LastChunkHasUsage()
    {
        // Arrange
        string sseContent = LoadChatCompletionsTraceFile("streaming/response.txt");

        // Act
        var chunks = ParseChatCompletionChunksFromSse(sseContent);
        var lastChunkJson = chunks.Last();
        var lastChunk = JsonSerializer.Deserialize(lastChunkJson.GetRawText(), ChatCompletions.ChatCompletionsJsonContext.Default.ChatCompletionChunk);

        // Assert
        Assert.NotNull(lastChunk);
        Assert.NotNull(lastChunk.Usage);
        Assert.True(lastChunk.Usage.PromptTokens > 0);
        Assert.True(lastChunk.Usage.CompletionTokens > 0);
        Assert.Equal(lastChunk.Usage.PromptTokens + lastChunk.Usage.CompletionTokens, lastChunk.Usage.TotalTokens);
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

            if (line.StartsWith("data: ", StringComparison.Ordinal))
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

    #endregion
}
