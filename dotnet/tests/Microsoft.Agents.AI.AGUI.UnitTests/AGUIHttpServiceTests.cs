// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Linq;
using System.Net;
using System.Net.Http;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.AI.AGUI.Shared;
using Moq;
using Moq.Protected;

namespace Microsoft.Agents.AI.AGUI.UnitTests;

/// <summary>
/// Unit tests for the <see cref="AGUIHttpService"/> class.
/// </summary>
public sealed class AGUIHttpServiceTests
{
    [Fact]
    public async Task PostRunAsync_SendsRequestAndParsesSSEStream_SuccessfullyAsync()
    {
        // Arrange
        BaseEvent[] events = new BaseEvent[]
        {
            new RunStartedEvent { ThreadId = "thread1", RunId = "run1" },
            new TextMessageStartEvent { MessageId = "msg1", Role = AGUIRoles.Assistant },
            new TextMessageContentEvent { MessageId = "msg1", Delta = "Hello" },
            new TextMessageEndEvent { MessageId = "msg1" },
            new RunFinishedEvent { ThreadId = "thread1", RunId = "run1" }
        };

        HttpClient httpClient = this.CreateMockHttpClient(events, HttpStatusCode.OK);
        AGUIHttpService service = new(httpClient, "http://localhost/agent");
        RunAgentInput input = new()
        {
            ThreadId = "thread1",
            RunId = "run1",
            Messages = [new AGUIUserMessage { Id = "m1", Content = "Test" }]
        };

        // Act
        List<BaseEvent> resultEvents = [];
        await foreach (BaseEvent evt in service.PostRunAsync(input, CancellationToken.None))
        {
            resultEvents.Add(evt);
        }

        // Assert
        Assert.Equal(5, resultEvents.Count);
        Assert.IsType<RunStartedEvent>(resultEvents[0]);
        Assert.IsType<TextMessageStartEvent>(resultEvents[1]);
        Assert.IsType<TextMessageContentEvent>(resultEvents[2]);
        Assert.IsType<TextMessageEndEvent>(resultEvents[3]);
        Assert.IsType<RunFinishedEvent>(resultEvents[4]);
    }

    [Fact]
    public async Task PostRunAsync_WithNonSuccessStatusCode_ThrowsHttpRequestExceptionAsync()
    {
        // Arrange
        HttpClient httpClient = this.CreateMockHttpClient([], HttpStatusCode.InternalServerError);
        AGUIHttpService service = new(httpClient, "http://localhost/agent");
        RunAgentInput input = new()
        {
            ThreadId = "thread1",
            RunId = "run1",
            Messages = [new AGUIUserMessage { Id = "m1", Content = "Test" }]
        };

        // Act & Assert
        await Assert.ThrowsAsync<HttpRequestException>(async () =>
        {
            await foreach (var _ in service.PostRunAsync(input, CancellationToken.None))
            {
                // Consume the stream
            }
        });
    }

    [Fact]
    public async Task PostRunAsync_DeserializesMultipleEventTypes_CorrectlyAsync()
    {
        // Arrange
        BaseEvent[] events = new BaseEvent[]
        {
            new RunStartedEvent { ThreadId = "thread1", RunId = "run1" },
            new RunErrorEvent { Message = "Error occurred", Code = "ERR001" },
            new RunFinishedEvent { ThreadId = "thread1", RunId = "run1", Result = JsonDocument.Parse("\"Success\"").RootElement.Clone() }
        };

        HttpClient httpClient = this.CreateMockHttpClient(events, HttpStatusCode.OK);
        AGUIHttpService service = new(httpClient, "http://localhost/agent");
        RunAgentInput input = new()
        {
            ThreadId = "thread1",
            RunId = "run1",
            Messages = [new AGUIUserMessage { Id = "m1", Content = "Test" }]
        };

        // Act
        List<BaseEvent> resultEvents = [];
        await foreach (BaseEvent evt in service.PostRunAsync(input, CancellationToken.None))
        {
            resultEvents.Add(evt);
        }

        // Assert
        Assert.Equal(3, resultEvents.Count);
        RunStartedEvent startedEvent = Assert.IsType<RunStartedEvent>(resultEvents[0]);
        Assert.Equal("thread1", startedEvent.ThreadId);
        RunErrorEvent errorEvent = Assert.IsType<RunErrorEvent>(resultEvents[1]);
        Assert.Equal("Error occurred", errorEvent.Message);
        RunFinishedEvent finishedEvent = Assert.IsType<RunFinishedEvent>(resultEvents[2]);
        Assert.Equal("Success", finishedEvent.Result?.GetString());
    }

    [Fact]
    public async Task PostRunAsync_WithEmptyEventStream_CompletesSuccessfullyAsync()
    {
        // Arrange
        HttpClient httpClient = this.CreateMockHttpClient([], HttpStatusCode.OK);
        AGUIHttpService service = new(httpClient, "http://localhost/agent");
        RunAgentInput input = new()
        {
            ThreadId = "thread1",
            RunId = "run1",
            Messages = [new AGUIUserMessage { Id = "m1", Content = "Test" }]
        };

        // Act
        List<BaseEvent> resultEvents = [];
        await foreach (BaseEvent evt in service.PostRunAsync(input, CancellationToken.None))
        {
            resultEvents.Add(evt);
        }

        // Assert
        Assert.Empty(resultEvents);
    }

    [Fact]
    public async Task PostRunAsync_WithCancellationToken_CancelsRequestAsync()
    {
        // Arrange
        CancellationTokenSource cts = new();
        cts.Cancel();

        Mock<HttpMessageHandler> handlerMock = new(MockBehavior.Strict);
        handlerMock
            .Protected()
            .Setup<Task<HttpResponseMessage>>(
                "SendAsync",
                ItExpr.IsAny<HttpRequestMessage>(),
                ItExpr.IsAny<CancellationToken>())
            .ThrowsAsync(new TaskCanceledException());

        HttpClient httpClient = new(handlerMock.Object);
        AGUIHttpService service = new(httpClient, "http://localhost/agent");
        RunAgentInput input = new()
        {
            ThreadId = "thread1",
            RunId = "run1",
            Messages = [new AGUIUserMessage { Id = "m1", Content = "Test" }]
        };

        // Act & Assert
        await Assert.ThrowsAsync<TaskCanceledException>(async () =>
        {
            await foreach (var _ in service.PostRunAsync(input, cts.Token))
            {
                // Intentionally empty - consuming stream to trigger cancellation
            }
        });
    }

    private HttpClient CreateMockHttpClient(BaseEvent[] events, HttpStatusCode statusCode)
    {
        string sseContent = string.Join("", events.Select(e =>
            $"data: {JsonSerializer.Serialize(e, AGUIJsonSerializerContext.Default.BaseEvent)}\n\n"));

        Mock<HttpMessageHandler> handlerMock = new(MockBehavior.Strict);
        handlerMock
            .Protected()
            .Setup<Task<HttpResponseMessage>>(
                "SendAsync",
                ItExpr.IsAny<HttpRequestMessage>(),
                ItExpr.IsAny<CancellationToken>())
            .ReturnsAsync(new HttpResponseMessage
            {
                StatusCode = statusCode,
                Content = new StringContent(sseContent)
            });

        return new HttpClient(handlerMock.Object);
    }
}
