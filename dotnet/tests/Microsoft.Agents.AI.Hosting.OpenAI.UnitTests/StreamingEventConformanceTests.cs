// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Net.Http;
using System.Text.Json;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Hosting.OpenAI.Responses.Models;
using Microsoft.Agents.AI.Hosting.OpenAI.Tests;

namespace Microsoft.Agents.AI.Hosting.OpenAI.UnitTests;

/// <summary>
/// Tests that verify our implementation generates correctly formatted streaming Server-Sent Events (SSE)
/// that conform to the OpenAI Response API streaming response format.
/// These tests validate the actual server implementation behavior by creating test servers
/// and verifying the SSE output matches expected formats.
/// For pure event deserialization tests, see OpenAIResponsesSerializationTests.
/// </summary>
public sealed class StreamingEventConformanceTests : ConformanceTestBase
{
    [Fact]
    public async Task ParseStreamingEvents_BasicFormat_SuccessAsync()
    {
        // Arrange
        string requestJson = LoadResponsesTraceFile("streaming/request.json");
        string expectedSseContent = LoadResponsesTraceFile("streaming/response.txt");

        // Extract expected text
        var expectedEvents = ParseSseEvents(expectedSseContent);
        var deltaEvents = expectedEvents.Where(e => e.GetProperty("type").GetString() == "response.output_text.delta").ToList();
        string expectedText = string.Concat(deltaEvents.Select(e => e.GetProperty("delta").GetString()));

        HttpClient client = await this.CreateTestServerAsync("streaming-basic-agent", "You are a helpful assistant.", expectedText);

        // Act
        HttpResponseMessage httpResponse = await this.SendResponsesRequestAsync(client, "streaming-basic-agent", requestJson);
        string sseContent = await httpResponse.Content.ReadAsStringAsync();

        // Act
        var events = ParseSseEvents(sseContent);

        // Assert
        Assert.NotEmpty(events);
        Assert.All(events, evt =>
        {
            Assert.True(evt.TryGetProperty("type", out var type));
            Assert.True(evt.TryGetProperty("sequence_number", out var seqNum));
            Assert.Equal(JsonValueKind.Number, seqNum.ValueKind);
        });
    }

    [Fact]
    public async Task ParseStreamingEvents_HasCorrectEventTypesAsync()
    {
        // Arrange
        string requestJson = LoadResponsesTraceFile("streaming/request.json");
        string expectedSseContent = LoadResponsesTraceFile("streaming/response.txt");

        var expectedEvents = ParseSseEvents(expectedSseContent);
        var deltaEvents = expectedEvents.Where(e => e.GetProperty("type").GetString() == "response.output_text.delta").ToList();
        string expectedText = string.Concat(deltaEvents.Select(e => e.GetProperty("delta").GetString()));

        HttpClient client = await this.CreateTestServerAsync("streaming-types-agent", "You are a helpful assistant.", expectedText);

        // Act
        HttpResponseMessage httpResponse = await this.SendResponsesRequestAsync(client, "streaming-types-agent", requestJson);

        // Assert - HTTP response validation
        Assert.Equal(System.Net.HttpStatusCode.OK, httpResponse.StatusCode);
        Assert.Equal("text/event-stream", httpResponse.Content.Headers.ContentType?.MediaType);

        string sseContent = await httpResponse.Content.ReadAsStringAsync();

        // Act
        var events = ParseSseEvents(sseContent);
        List<string> eventTypes = events.ConvertAll(e => e.GetProperty("type").GetString()!);

        // Assert - Verify all required event types are present
        Assert.Contains("response.created", eventTypes);
        Assert.Contains("response.in_progress", eventTypes);
        Assert.Contains("response.output_item.added", eventTypes);
        Assert.Contains("response.content_part.added", eventTypes);
        Assert.Contains("response.output_text.delta", eventTypes);
        Assert.Contains("response.output_text.done", eventTypes);
        Assert.Contains("response.content_part.done", eventTypes);
        Assert.Contains("response.output_item.done", eventTypes);

        // Assert - Verify the order of events
        Assert.Equal("response.created", eventTypes[0]);
        Assert.Equal("response.in_progress", eventTypes[1]);

        // Find indices of key events to verify ordering
        int outputItemAddedIndex = eventTypes.IndexOf("response.output_item.added");
        int contentPartAddedIndex = eventTypes.IndexOf("response.content_part.added");
        int firstDeltaIndex = eventTypes.IndexOf("response.output_text.delta");
        int textDoneIndex = eventTypes.IndexOf("response.output_text.done");
        int contentPartDoneIndex = eventTypes.IndexOf("response.content_part.done");
        int outputItemDoneIndex = eventTypes.IndexOf("response.output_item.done");

        Assert.True(outputItemAddedIndex < contentPartAddedIndex, "output_item.added should come before content_part.added");
        Assert.True(contentPartAddedIndex < firstDeltaIndex, "content_part.added should come before first output_text.delta");
        Assert.True(firstDeltaIndex < textDoneIndex, "output_text.delta should come before output_text.done");
        Assert.True(textDoneIndex < contentPartDoneIndex, "output_text.done should come before content_part.done");
        Assert.True(contentPartDoneIndex < outputItemDoneIndex, "content_part.done should come before output_item.done");

        // Assert - Last event should be a terminal state
        string lastEventType = eventTypes[^1];
        Assert.True(
            lastEventType is "response.completed" or
            "response.incomplete" or
            "response.failed",
            $"Last event should be a terminal state, got: {lastEventType}");
    }

    [Fact]
    public async Task ParseStreamingEvents_DeserializeCreatedEvent_SuccessAsync()
    {
        // Arrange
        string requestJson = LoadResponsesTraceFile("streaming/request.json");
        string expectedSseContent = LoadResponsesTraceFile("streaming/response.txt");

        var expectedEvents = ParseSseEvents(expectedSseContent);
        var deltaEvents = expectedEvents.Where(e => e.GetProperty("type").GetString() == "response.output_text.delta").ToList();
        string expectedText = string.Concat(deltaEvents.Select(e => e.GetProperty("delta").GetString()));

        HttpClient client = await this.CreateTestServerAsync("streaming-created-agent", "You are a helpful assistant.", expectedText);

        // Act
        HttpResponseMessage httpResponse = await this.SendResponsesRequestAsync(client, "streaming-created-agent", requestJson);
        string sseContent = await httpResponse.Content.ReadAsStringAsync();
        var events = ParseSseEvents(sseContent);
        var createdEventJson = events.First(e => e.GetProperty("type").GetString() == "response.created");

        // Act
        string jsonString = createdEventJson.GetRawText();
        StreamingResponseEvent? evt = JsonSerializer.Deserialize(jsonString, OpenAIHostingJsonContext.Default.StreamingResponseEvent);

        // Assert
        Assert.NotNull(evt);
        Assert.IsType<StreamingResponseCreated>(evt);
        var created = (StreamingResponseCreated)evt;
        Assert.Equal(0, created.SequenceNumber);
        Assert.NotNull(created.Response);
        Assert.NotNull(created.Response.Id);
        Assert.StartsWith("resp_", created.Response.Id);
    }

    [Fact]
    public async Task ParseStreamingEvents_DeserializeInProgressEvent_SuccessAsync()
    {
        // Arrange
        string requestJson = LoadResponsesTraceFile("streaming/request.json");
        string expectedSseContent = LoadResponsesTraceFile("streaming/response.txt");

        var expectedEvents = ParseSseEvents(expectedSseContent);
        var deltaEvents = expectedEvents.Where(e => e.GetProperty("type").GetString() == "response.output_text.delta").ToList();
        string expectedText = string.Concat(deltaEvents.Select(e => e.GetProperty("delta").GetString()));

        HttpClient client = await this.CreateTestServerAsync("streaming-progress-agent", "You are a helpful assistant.", expectedText);

        // Act
        HttpResponseMessage httpResponse = await this.SendResponsesRequestAsync(client, "streaming-progress-agent", requestJson);
        string sseContent = await httpResponse.Content.ReadAsStringAsync();
        var events = ParseSseEvents(sseContent);
        var inProgressEventJson = events.First(e => e.GetProperty("type").GetString() == "response.in_progress");

        // Act
        string jsonString = inProgressEventJson.GetRawText();
        StreamingResponseEvent? evt = JsonSerializer.Deserialize(jsonString, OpenAIHostingJsonContext.Default.StreamingResponseEvent);

        // Assert
        Assert.NotNull(evt);
        Assert.IsType<StreamingResponseInProgress>(evt);
        var inProgress = (StreamingResponseInProgress)evt;
        Assert.Equal(1, inProgress.SequenceNumber);
        Assert.NotNull(inProgress.Response);
        Assert.Equal(ResponseStatus.InProgress, inProgress.Response.Status);
    }

    [Fact]
    public async Task ParseStreamingEvents_DeserializeOutputItemAdded_SuccessAsync()
    {
        // Arrange
        string requestJson = LoadResponsesTraceFile("streaming/request.json");
        string expectedSseContent = LoadResponsesTraceFile("streaming/response.txt");

        var expectedEvents = ParseSseEvents(expectedSseContent);
        var deltaEvents = expectedEvents.Where(e => e.GetProperty("type").GetString() == "response.output_text.delta").ToList();
        string expectedText = string.Concat(deltaEvents.Select(e => e.GetProperty("delta").GetString()));

        HttpClient client = await this.CreateTestServerAsync("streaming-item-agent", "You are a helpful assistant.", expectedText);

        // Act
        HttpResponseMessage httpResponse = await this.SendResponsesRequestAsync(client, "streaming-item-agent", requestJson);
        string sseContent = await httpResponse.Content.ReadAsStringAsync();
        var events = ParseSseEvents(sseContent);
        var itemAddedJson = events.First(e => e.GetProperty("type").GetString() == "response.output_item.added");

        // Act
        string jsonString = itemAddedJson.GetRawText();
        StreamingResponseEvent? evt = JsonSerializer.Deserialize(jsonString, OpenAIHostingJsonContext.Default.StreamingResponseEvent);

        // Assert
        Assert.NotNull(evt);
        Assert.IsType<StreamingOutputItemAdded>(evt);
        var itemAdded = (StreamingOutputItemAdded)evt;
        Assert.Equal(0, itemAdded.OutputIndex);
        Assert.NotNull(itemAdded.Item);
    }

    [Fact]
    public async Task ParseStreamingEvents_DeserializeContentPartAdded_SuccessAsync()
    {
        // Arrange
        string requestJson = LoadResponsesTraceFile("streaming/request.json");
        string expectedSseContent = LoadResponsesTraceFile("streaming/response.txt");

        var expectedEvents = ParseSseEvents(expectedSseContent);
        var deltaEvents = expectedEvents.Where(e => e.GetProperty("type").GetString() == "response.output_text.delta").ToList();
        string expectedText = string.Concat(deltaEvents.Select(e => e.GetProperty("delta").GetString()));

        HttpClient client = await this.CreateTestServerAsync("streaming-part-agent", "You are a helpful assistant.", expectedText);

        // Act
        HttpResponseMessage httpResponse = await this.SendResponsesRequestAsync(client, "streaming-part-agent", requestJson);
        string sseContent = await httpResponse.Content.ReadAsStringAsync();
        var events = ParseSseEvents(sseContent);
        var partAddedJson = events.First(e => e.GetProperty("type").GetString() == "response.content_part.added");

        // Act
        string jsonString = partAddedJson.GetRawText();
        StreamingResponseEvent? evt = JsonSerializer.Deserialize(jsonString, OpenAIHostingJsonContext.Default.StreamingResponseEvent);

        // Assert
        Assert.NotNull(evt);
        Assert.IsType<StreamingContentPartAdded>(evt);
        var partAdded = (StreamingContentPartAdded)evt;
        Assert.NotNull(partAdded.ItemId);
        Assert.Equal(0, partAdded.OutputIndex);
        Assert.Equal(0, partAdded.ContentIndex);
        Assert.NotNull(partAdded.Part);
    }

    [Fact]
    public async Task ParseStreamingEvents_DeserializeTextDelta_SuccessAsync()
    {
        // Arrange
        string requestJson = LoadResponsesTraceFile("streaming/request.json");
        string expectedSseContent = LoadResponsesTraceFile("streaming/response.txt");

        var expectedEvents = ParseSseEvents(expectedSseContent);
        var deltaEvents = expectedEvents.Where(e => e.GetProperty("type").GetString() == "response.output_text.delta").ToList();
        string expectedText = string.Concat(deltaEvents.Select(e => e.GetProperty("delta").GetString()));

        HttpClient client = await this.CreateTestServerAsync("streaming-delta-agent", "You are a helpful assistant.", expectedText);

        // Act
        HttpResponseMessage httpResponse = await this.SendResponsesRequestAsync(client, "streaming-delta-agent", requestJson);
        string sseContent = await httpResponse.Content.ReadAsStringAsync();
        var events = ParseSseEvents(sseContent);
        var textDeltaJson = events.First(e => e.GetProperty("type").GetString() == "response.output_text.delta");

        // Act
        string jsonString = textDeltaJson.GetRawText();
        StreamingResponseEvent? evt = JsonSerializer.Deserialize(jsonString, OpenAIHostingJsonContext.Default.StreamingResponseEvent);

        // Assert
        Assert.NotNull(evt);
        Assert.IsType<StreamingOutputTextDelta>(evt);
        var textDelta = (StreamingOutputTextDelta)evt;
        Assert.NotNull(textDelta.ItemId);
        Assert.Equal(0, textDelta.OutputIndex);
        Assert.Equal(0, textDelta.ContentIndex);
        Assert.NotNull(textDelta.Delta);
    }

    [Fact]
    public async Task ParseStreamingEvents_AccumulateTextDeltas_MatchesFinalTextAsync()
    {
        // Arrange
        string requestJson = LoadResponsesTraceFile("streaming/request.json");
        string expectedSseContent = LoadResponsesTraceFile("streaming/response.txt");

        var expectedEvents = ParseSseEvents(expectedSseContent);
        var deltaEvents = expectedEvents.Where(e => e.GetProperty("type").GetString() == "response.output_text.delta").ToList();
        string expectedText = string.Concat(deltaEvents.Select(e => e.GetProperty("delta").GetString()));

        HttpClient client = await this.CreateTestServerAsync("streaming-accumulate-agent", "You are a helpful assistant.", expectedText);

        // Act
        HttpResponseMessage httpResponse = await this.SendResponsesRequestAsync(client, "streaming-accumulate-agent", requestJson);
        string sseContent = await httpResponse.Content.ReadAsStringAsync();
        var events = ParseSseEvents(sseContent);

        // Act
        var deltas = new List<string>();
        string? finalText = null;

        foreach (var eventJson in events)
        {
            string jsonString = eventJson.GetRawText();
            StreamingResponseEvent? evt = JsonSerializer.Deserialize(jsonString, OpenAIHostingJsonContext.Default.StreamingResponseEvent);

            if (evt is StreamingOutputTextDelta delta)
            {
                deltas.Add(delta.Delta);
            }
            else if (evt is StreamingOutputTextDone done)
            {
                finalText = done.Text;
            }
        }

        // Assert
        Assert.NotEmpty(deltas);
        Assert.NotNull(finalText);

        string accumulated = string.Concat(deltas);
        Assert.Equal(accumulated, finalText);
    }

    [Fact]
    public async Task ParseStreamingEvents_SequenceNumbersAreSequentialAsync()
    {
        // Arrange
        string requestJson = LoadResponsesTraceFile("streaming/request.json");
        string expectedSseContent = LoadResponsesTraceFile("streaming/response.txt");

        var expectedEvents = ParseSseEvents(expectedSseContent);
        var deltaEvents = expectedEvents.Where(e => e.GetProperty("type").GetString() == "response.output_text.delta").ToList();
        string expectedText = string.Concat(deltaEvents.Select(e => e.GetProperty("delta").GetString()));

        HttpClient client = await this.CreateTestServerAsync("streaming-sequence-agent", "You are a helpful assistant.", expectedText);

        // Act
        HttpResponseMessage httpResponse = await this.SendResponsesRequestAsync(client, "streaming-sequence-agent", requestJson);
        string sseContent = await httpResponse.Content.ReadAsStringAsync();
        var events = ParseSseEvents(sseContent);

        // Act
        var sequenceNumbers = new List<int>();
        foreach (var eventJson in events)
        {
            string jsonString = eventJson.GetRawText();
            StreamingResponseEvent? evt = JsonSerializer.Deserialize(jsonString, OpenAIHostingJsonContext.Default.StreamingResponseEvent);
            Assert.NotNull(evt);
            sequenceNumbers.Add(evt.SequenceNumber);
        }

        // Assert
        Assert.NotEmpty(sequenceNumbers);
        Assert.Equal(0, sequenceNumbers.First());

        for (int i = 0; i < sequenceNumbers.Count; i++)
        {
            Assert.Equal(i, sequenceNumbers[i]);
        }
    }

    [Fact]
    public async Task ParseStreamingEvents_FinalEvent_IsTerminalStateAsync()
    {
        // Arrange
        string requestJson = LoadResponsesTraceFile("streaming/request.json");
        string expectedSseContent = LoadResponsesTraceFile("streaming/response.txt");

        var expectedEvents = ParseSseEvents(expectedSseContent);
        var deltaEvents = expectedEvents.Where(e => e.GetProperty("type").GetString() == "response.output_text.delta").ToList();
        string expectedText = string.Concat(deltaEvents.Select(e => e.GetProperty("delta").GetString()));

        HttpClient client = await this.CreateTestServerAsync("streaming-terminal-agent", "You are a helpful assistant.", expectedText);

        // Act
        HttpResponseMessage httpResponse = await this.SendResponsesRequestAsync(client, "streaming-terminal-agent", requestJson);
        string sseContent = await httpResponse.Content.ReadAsStringAsync();
        var events = ParseSseEvents(sseContent);
        var lastEventJson = events.Last();

        // Act
        string jsonString = lastEventJson.GetRawText();
        StreamingResponseEvent? evt = JsonSerializer.Deserialize(jsonString, OpenAIHostingJsonContext.Default.StreamingResponseEvent);

        // Assert
        Assert.NotNull(evt);

        // Should be one of the terminal events
        bool isTerminal = evt is StreamingResponseCompleted or
                          StreamingResponseIncomplete or
                          StreamingResponseFailed;
        Assert.True(isTerminal, $"Expected terminal event, got: {evt.GetType().Name}");
    }

    [Fact]
    public async Task ParseStreamingEvents_AllEvents_CanBeDeserializedAsync()
    {
        // Arrange
        string requestJson = LoadResponsesTraceFile("streaming/request.json");
        string expectedSseContent = LoadResponsesTraceFile("streaming/response.txt");

        var expectedEvents = ParseSseEvents(expectedSseContent);
        var deltaEvents = expectedEvents.Where(e => e.GetProperty("type").GetString() == "response.output_text.delta").ToList();
        string expectedText = string.Concat(deltaEvents.Select(e => e.GetProperty("delta").GetString()));

        HttpClient client = await this.CreateTestServerAsync("streaming-deserialize-agent", "You are a helpful assistant.", expectedText);

        // Act
        HttpResponseMessage httpResponse = await this.SendResponsesRequestAsync(client, "streaming-deserialize-agent", requestJson);
        string sseContent = await httpResponse.Content.ReadAsStringAsync();

        // Act & Assert
        foreach (var eventJson in ParseSseEvents(sseContent))
        {
            // Should not throw
            StreamingResponseEvent? evt = JsonSerializer.Deserialize(eventJson.GetRawText(), OpenAIHostingJsonContext.Default.StreamingResponseEvent);
            Assert.NotNull(evt);

            // Verify polymorphic deserialization worked
            Assert.True(
                evt is StreamingResponseCreated or
                StreamingResponseInProgress or
                StreamingResponseCompleted or
                StreamingResponseIncomplete or
                StreamingResponseFailed or
                StreamingOutputItemAdded or
                StreamingOutputItemDone or
                StreamingContentPartAdded or
                StreamingContentPartDone or
                StreamingOutputTextDelta or
                StreamingOutputTextDone or
                StreamingFunctionCallArgumentsDelta or
                StreamingFunctionCallArgumentsDone,
                $"Unknown event type: {evt.GetType().Name}");
        }
    }

    [Fact]
    public async Task ParseStreamingEvents_IdConsistency_ValidAsync()
    {
        // Arrange
        string requestJson = LoadResponsesTraceFile("streaming/request.json");
        string expectedSseContent = LoadResponsesTraceFile("streaming/response.txt");

        var expectedEvents = ParseSseEvents(expectedSseContent);
        var deltaEvents = expectedEvents.Where(e => e.GetProperty("type").GetString() == "response.output_text.delta").ToList();
        string expectedText = string.Concat(deltaEvents.Select(e => e.GetProperty("delta").GetString()));

        HttpClient client = await this.CreateTestServerAsync("streaming-id-agent", "You are a helpful assistant.", expectedText);

        // Act
        HttpResponseMessage httpResponse = await this.SendResponsesRequestAsync(client, "streaming-id-agent", requestJson);
        string sseContent = await httpResponse.Content.ReadAsStringAsync();
        var events = ParseSseEvents(sseContent);

        // Assert - Response ID consistency
        string? firstResponseId = null;

        foreach (var eventJson in events)
        {
            string jsonString = eventJson.GetRawText();
            StreamingResponseEvent? evt = JsonSerializer.Deserialize(jsonString, OpenAIHostingJsonContext.Default.StreamingResponseEvent);
            Assert.NotNull(evt);

            string? responseId = null;
            if (evt is StreamingResponseCreated created)
            {
                responseId = created.Response.Id;
                Assert.StartsWith("resp_", responseId);
            }
            else if (evt is StreamingResponseInProgress progress)
            {
                responseId = progress.Response.Id;
            }
            else if (evt is StreamingResponseCompleted completed)
            {
                responseId = completed.Response.Id;
            }
            else if (evt is StreamingResponseIncomplete incomplete)
            {
                responseId = incomplete.Response.Id;
            }
            else if (evt is StreamingResponseFailed failed)
            {
                responseId = failed.Response.Id;
            }

            if (responseId != null)
            {
                firstResponseId ??= responseId;
                Assert.Equal(firstResponseId, responseId);
            }
        }

        Assert.NotNull(firstResponseId);

        // Assert - Item ID consistency
        var itemIds = new HashSet<string>();
        foreach (var eventJson in events)
        {
            string jsonString = eventJson.GetRawText();
            StreamingResponseEvent? evt = JsonSerializer.Deserialize(jsonString, OpenAIHostingJsonContext.Default.StreamingResponseEvent);

            string? itemId = evt switch
            {
                StreamingOutputItemAdded added => added.Item.Id,
                StreamingOutputItemDone done => done.Item.Id,
                StreamingContentPartAdded partAdded => partAdded.ItemId,
                StreamingContentPartDone partDone => partDone.ItemId,
                StreamingOutputTextDelta textDelta => textDelta.ItemId,
                StreamingOutputTextDone textDone => textDone.ItemId,
                StreamingFunctionCallArgumentsDelta argsDelta => argsDelta.ItemId,
                StreamingFunctionCallArgumentsDone argsDone => argsDone.ItemId,
                _ => null
            };

            if (itemId != null)
            {
                Assert.NotEmpty(itemId);
                Assert.True(itemId.StartsWith("msg_", StringComparison.Ordinal) || itemId.StartsWith("fc_", StringComparison.Ordinal),
                    $"Item ID should start with 'msg_' or 'fc_', got: {itemId}");
                itemIds.Add(itemId);
            }
        }

        Assert.NotEmpty(itemIds);
    }

    [Fact]
    public async Task ParseStreamingEvents_IndexConsistency_ValidAsync()
    {
        // Arrange
        string requestJson = LoadResponsesTraceFile("streaming/request.json");
        string expectedSseContent = LoadResponsesTraceFile("streaming/response.txt");

        var expectedEvents = ParseSseEvents(expectedSseContent);
        var deltaEvents = expectedEvents.Where(e => e.GetProperty("type").GetString() == "response.output_text.delta").ToList();
        string expectedText = string.Concat(deltaEvents.Select(e => e.GetProperty("delta").GetString()));

        HttpClient client = await this.CreateTestServerAsync("streaming-index-agent", "You are a helpful assistant.", expectedText);

        // Act
        HttpResponseMessage httpResponse = await this.SendResponsesRequestAsync(client, "streaming-index-agent", requestJson);

        // Assert - All events with output_index should have valid values
        foreach (var eventJson in ParseSseEvents(await httpResponse.Content.ReadAsStringAsync()))
        {
            StreamingResponseEvent? evt = JsonSerializer.Deserialize(eventJson.GetRawText(), OpenAIHostingJsonContext.Default.StreamingResponseEvent);
            Assert.NotNull(evt);

            if (evt is StreamingOutputItemAdded or StreamingOutputItemDone or StreamingContentPartAdded or StreamingContentPartDone or
                StreamingOutputTextDelta or StreamingOutputTextDone or StreamingFunctionCallArgumentsDelta or StreamingFunctionCallArgumentsDone)
            {
                int outputIndex = evt switch
                {
                    StreamingOutputItemAdded added => added.OutputIndex,
                    StreamingOutputItemDone done => done.OutputIndex,
                    StreamingContentPartAdded partAdded => partAdded.OutputIndex,
                    StreamingContentPartDone partDone => partDone.OutputIndex,
                    StreamingOutputTextDelta textDelta => textDelta.OutputIndex,
                    StreamingOutputTextDone textDone => textDone.OutputIndex,
                    StreamingFunctionCallArgumentsDelta argsDelta => argsDelta.OutputIndex,
                    StreamingFunctionCallArgumentsDone argsDone => argsDone.OutputIndex,
                    _ => -1
                };

                Assert.True(outputIndex >= 0, $"output_index should be non-negative, got: {outputIndex}");
            }

            if (evt is StreamingContentPartAdded or StreamingContentPartDone or StreamingOutputTextDelta or StreamingOutputTextDone)
            {
                int contentIndex = evt switch
                {
                    StreamingContentPartAdded partAdded => partAdded.ContentIndex,
                    StreamingContentPartDone partDone => partDone.ContentIndex,
                    StreamingOutputTextDelta textDelta => textDelta.ContentIndex,
                    StreamingOutputTextDone textDone => textDone.ContentIndex,
                    _ => -1
                };

                Assert.True(contentIndex >= 0, $"content_index should be non-negative, got: {contentIndex}");
            }
        }
    }

    [Fact]
    public async Task ParseStreamingEvents_ResponseObjectEvolution_ValidAsync()
    {
        // Arrange
        string requestJson = LoadResponsesTraceFile("streaming/request.json");
        string expectedSseContent = LoadResponsesTraceFile("streaming/response.txt");

        var expectedEvents = ParseSseEvents(expectedSseContent);
        var deltaEvents = expectedEvents.Where(e => e.GetProperty("type").GetString() == "response.output_text.delta").ToList();
        string expectedText = string.Concat(deltaEvents.Select(e => e.GetProperty("delta").GetString()));

        HttpClient client = await this.CreateTestServerAsync("streaming-evolution-agent", "You are a helpful assistant.", expectedText);

        // Act
        HttpResponseMessage httpResponse = await this.SendResponsesRequestAsync(client, "streaming-evolution-agent", requestJson);
        string sseContent = await httpResponse.Content.ReadAsStringAsync();
        var events = ParseSseEvents(sseContent);

        Response? createdResponse = null;
        Response? terminalResponse = null;

        foreach (var eventJson in events)
        {
            string jsonString = eventJson.GetRawText();
            StreamingResponseEvent? evt = JsonSerializer.Deserialize(jsonString, OpenAIHostingJsonContext.Default.StreamingResponseEvent);
            Assert.NotNull(evt);

            if (evt is StreamingResponseCreated created)
            {
                createdResponse = created.Response;
                Assert.Equal(ResponseStatus.InProgress, createdResponse.Status);
                Assert.Empty(createdResponse.Output);
                // Usage may be null or zero'd out in created event
                if (createdResponse.Usage != null)
                {
                    Assert.Equal(0, createdResponse.Usage.InputTokens);
                    Assert.Equal(0, createdResponse.Usage.OutputTokens);
                }
            }
            else if (evt is StreamingResponseInProgress progress)
            {
                Assert.Equal(ResponseStatus.InProgress, progress.Response.Status);
            }
            else if (evt is StreamingResponseCompleted completed)
            {
                terminalResponse = completed.Response;
                Assert.Equal(ResponseStatus.Completed, terminalResponse.Status);
                Assert.NotEmpty(terminalResponse.Output);
                Assert.NotNull(terminalResponse.Usage);
                Assert.True(terminalResponse.Usage.InputTokens > 0);
                Assert.True(terminalResponse.Usage.OutputTokens > 0);
            }
            else if (evt is StreamingResponseIncomplete incomplete)
            {
                terminalResponse = incomplete.Response;
                Assert.Equal(ResponseStatus.Incomplete, terminalResponse.Status);
            }
            else if (evt is StreamingResponseFailed failed)
            {
                terminalResponse = failed.Response;
                Assert.Equal(ResponseStatus.Failed, terminalResponse.Status);
            }
        }

        Assert.NotNull(createdResponse);
        Assert.NotNull(terminalResponse);
    }

    [Fact]
    public async Task ParseStreamingEvents_SseFormatCompliance_ValidAsync()
    {
        // Arrange
        string requestJson = LoadResponsesTraceFile("streaming/request.json");
        string expectedSseContent = LoadResponsesTraceFile("streaming/response.txt");

        var expectedEvents = ParseSseEvents(expectedSseContent);
        var deltaEvents = expectedEvents.Where(e => e.GetProperty("type").GetString() == "response.output_text.delta").ToList();
        string expectedText = string.Concat(deltaEvents.Select(e => e.GetProperty("delta").GetString()));

        HttpClient client = await this.CreateTestServerAsync("streaming-sse-agent", "You are a helpful assistant.", expectedText);

        // Act
        HttpResponseMessage httpResponse = await this.SendResponsesRequestAsync(client, "streaming-sse-agent", requestJson);
        string sseContent = await httpResponse.Content.ReadAsStringAsync();

        // Assert - SSE format validation
        var lines = sseContent.Split('\n');
        Assert.NotEmpty(lines);

        for (int i = 0; i < lines.Length; i++)
        {
            string line = lines[i].TrimEnd('\r');

            if (line.StartsWith("event: ", StringComparison.Ordinal))
            {
                // Every "event:" line must be followed by a "data:" line
                Assert.True(i + 1 < lines.Length, $"Event at line {i} has no following data line");
                string nextLine = lines[i + 1].TrimEnd('\r');
                Assert.True(nextLine.StartsWith("data: ", StringComparison.Ordinal),
                    $"Line after event: should be data:, got: {nextLine}");

                // Validate the data line contains valid JSON
                string jsonData = nextLine.Substring("data: ".Length);
                Assert.NotEmpty(jsonData);

                // Should be parseable as JSON
                Exception? parseException = Record.Exception(() => JsonDocument.Parse(jsonData));
                Assert.Null(parseException);
            }
        }
    }

    [Fact]
    public async Task ParseStreamingEvents_EventPairing_ValidAsync()
    {
        // Arrange
        string requestJson = LoadResponsesTraceFile("streaming/request.json");
        string expectedSseContent = LoadResponsesTraceFile("streaming/response.txt");

        var expectedEvents = ParseSseEvents(expectedSseContent);
        var deltaEvents = expectedEvents.Where(e => e.GetProperty("type").GetString() == "response.output_text.delta").ToList();
        string expectedText = string.Concat(deltaEvents.Select(e => e.GetProperty("delta").GetString()));

        HttpClient client = await this.CreateTestServerAsync("streaming-pairing-agent", "You are a helpful assistant.", expectedText);

        // Act
        HttpResponseMessage httpResponse = await this.SendResponsesRequestAsync(client, "streaming-pairing-agent", requestJson);
        string sseContent = await httpResponse.Content.ReadAsStringAsync();
        var events = ParseSseEvents(sseContent);

        // Track added vs done events
        var outputItemsAdded = new HashSet<int>();
        var outputItemsDone = new HashSet<int>();
        var contentPartsAdded = new List<(int outputIndex, int contentIndex)>();
        var contentPartsDone = new List<(int outputIndex, int contentIndex)>();

        foreach (var eventJson in events)
        {
            string jsonString = eventJson.GetRawText();
            StreamingResponseEvent? evt = JsonSerializer.Deserialize(jsonString, OpenAIHostingJsonContext.Default.StreamingResponseEvent);
            Assert.NotNull(evt);

            switch (evt)
            {
                case StreamingOutputItemAdded added:
                    outputItemsAdded.Add(added.OutputIndex);
                    break;
                case StreamingOutputItemDone done:
                    outputItemsDone.Add(done.OutputIndex);
                    // Every done must have a corresponding added
                    Assert.Contains(done.OutputIndex, outputItemsAdded);
                    break;
                case StreamingContentPartAdded partAdded:
                    contentPartsAdded.Add((partAdded.OutputIndex, partAdded.ContentIndex));
                    break;
                case StreamingContentPartDone partDone:
                    contentPartsDone.Add((partDone.OutputIndex, partDone.ContentIndex));
                    // Every done must have a corresponding added
                    Assert.Contains((partDone.OutputIndex, partDone.ContentIndex), contentPartsAdded);
                    break;
            }
        }

        // All added items should eventually be done
        Assert.Equal(outputItemsAdded.Count, outputItemsDone.Count);
        Assert.Equal(contentPartsAdded.Count, contentPartsDone.Count);
    }

    [Fact]
    public async Task ParseStreamingEvents_NoDuplicateSequenceNumbers_ValidAsync()
    {
        // Arrange
        string requestJson = LoadResponsesTraceFile("streaming/request.json");
        string expectedSseContent = LoadResponsesTraceFile("streaming/response.txt");

        var expectedEvents = ParseSseEvents(expectedSseContent);
        var deltaEvents = expectedEvents.Where(e => e.GetProperty("type").GetString() == "response.output_text.delta").ToList();
        string expectedText = string.Concat(deltaEvents.Select(e => e.GetProperty("delta").GetString()));

        HttpClient client = await this.CreateTestServerAsync("streaming-nodup-agent", "You are a helpful assistant.", expectedText);

        // Act
        HttpResponseMessage httpResponse = await this.SendResponsesRequestAsync(client, "streaming-nodup-agent", requestJson);
        string sseContent = await httpResponse.Content.ReadAsStringAsync();
        var events = ParseSseEvents(sseContent);

        // Assert - No duplicate sequence numbers
        var sequenceNumbers = new HashSet<int>();
        foreach (var eventJson in events)
        {
            string jsonString = eventJson.GetRawText();
            StreamingResponseEvent? evt = JsonSerializer.Deserialize(jsonString, OpenAIHostingJsonContext.Default.StreamingResponseEvent);
            Assert.NotNull(evt);

            Assert.True(sequenceNumbers.Add(evt.SequenceNumber),
                $"Duplicate sequence number found: {evt.SequenceNumber}");
        }
    }

    /// <summary>
    /// Helper to parse SSE events from streaming response content.
    /// </summary>
    private static List<JsonElement> ParseSseEvents(string sseContent)
    {
        var events = new List<JsonElement>();
        var lines = sseContent.Split('\n');

        for (int i = 0; i < lines.Length; i++)
        {
            var line = lines[i].TrimEnd('\r');

            if (line.StartsWith("event: ", StringComparison.Ordinal))
            {
                // Next line should have the data
                if (i + 1 < lines.Length)
                {
                    var dataLine = lines[i + 1].TrimEnd('\r');
                    if (dataLine.StartsWith("data: ", StringComparison.Ordinal))
                    {
                        var jsonData = dataLine.Substring("data: ".Length);
                        var doc = JsonDocument.Parse(jsonData);
                        events.Add(doc.RootElement.Clone());
                    }
                }
            }
        }

        return events;
    }
}
