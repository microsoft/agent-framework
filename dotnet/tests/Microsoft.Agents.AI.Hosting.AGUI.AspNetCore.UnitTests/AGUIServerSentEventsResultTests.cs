// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.IO;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Hosting.AGUI.AspNetCore.Shared;
using Microsoft.AspNetCore.Http;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Logging.Abstractions;

namespace Microsoft.Agents.AI.Hosting.AGUI.AspNetCore.UnitTests;

/// <summary>
/// Unit tests for the <see cref="AGUIServerSentEventsResult"/> class.
/// </summary>
public sealed class AGUIServerSentEventsResultTests
{
    [Fact]
    public async Task ExecuteAsync_SetsCorrectResponseHeaders_ContentTypeAndCacheControlAsync()
    {
        // Arrange
        List<BaseEvent> events = [];
        ILogger<AGUIServerSentEventsResult> logger = NullLogger<AGUIServerSentEventsResult>.Instance;
        AGUIServerSentEventsResult result = new(events.ToAsyncEnumerableAsync(), logger);
        DefaultHttpContext httpContext = new();
        httpContext.Response.Body = new MemoryStream();

        // Act
        await result.ExecuteAsync(httpContext);

        // Assert
        Assert.Equal("text/event-stream", httpContext.Response.ContentType);
        Assert.Equal("no-cache,no-store", httpContext.Response.Headers.CacheControl.ToString());
        Assert.Equal("no-cache", httpContext.Response.Headers.Pragma.ToString());
    }

    [Fact]
    public async Task ExecuteAsync_SerializesEventsInSSEFormat_WithDataPrefixAndNewlinesAsync()
    {
        // Arrange
        List<BaseEvent> events =
        [
            new RunStartedEvent { ThreadId = "thread1", RunId = "run1" },
            new RunFinishedEvent { ThreadId = "thread1", RunId = "run1" }
        ];
        ILogger<AGUIServerSentEventsResult> logger = NullLogger<AGUIServerSentEventsResult>.Instance;
        AGUIServerSentEventsResult result = new(events.ToAsyncEnumerableAsync(), logger);
        DefaultHttpContext httpContext = new();
        MemoryStream responseStream = new();
        httpContext.Response.Body = responseStream;

        // Act
        await result.ExecuteAsync(httpContext);

        // Assert
        string responseContent = Encoding.UTF8.GetString(responseStream.ToArray());
        Assert.Contains("data: ", responseContent);
        Assert.Contains("\n\n", responseContent);
        string[] eventStrings = responseContent.Split("\n\n", StringSplitOptions.RemoveEmptyEntries);
        Assert.Equal(2, eventStrings.Length);
    }

    [Fact]
    public async Task ExecuteAsync_FlushesResponse_AfterEachEventAsync()
    {
        // Arrange
        List<BaseEvent> events =
        [
            new RunStartedEvent { ThreadId = "thread1", RunId = "run1" },
            new TextMessageContentEvent { MessageId = "msg1", Delta = "Hello" },
            new RunFinishedEvent { ThreadId = "thread1", RunId = "run1" }
        ];
        ILogger<AGUIServerSentEventsResult> logger = NullLogger<AGUIServerSentEventsResult>.Instance;
        AGUIServerSentEventsResult result = new(events.ToAsyncEnumerableAsync(), logger);
        DefaultHttpContext httpContext = new();
        MemoryStream responseStream = new();
        httpContext.Response.Body = responseStream;

        // Act
        await result.ExecuteAsync(httpContext);

        // Assert
        string responseContent = Encoding.UTF8.GetString(responseStream.ToArray());
        string[] eventStrings = responseContent.Split("\n\n", StringSplitOptions.RemoveEmptyEntries);
        Assert.Equal(3, eventStrings.Length);
    }

    [Fact]
    public async Task ExecuteAsync_WithEmptyEventStream_CompletesSuccessfullyAsync()
    {
        // Arrange
        List<BaseEvent> events = [];
        ILogger<AGUIServerSentEventsResult> logger = NullLogger<AGUIServerSentEventsResult>.Instance;
        AGUIServerSentEventsResult result = new(events.ToAsyncEnumerableAsync(), logger);
        DefaultHttpContext httpContext = new();
        httpContext.Response.Body = new MemoryStream();

        // Act
        await result.ExecuteAsync(httpContext);

        // Assert
        Assert.Equal(StatusCodes.Status200OK, result.StatusCode);
    }

    [Fact]
    public async Task ExecuteAsync_RespectsCancellationToken_WhenCancelledAsync()
    {
        // Arrange
        using CancellationTokenSource cts = new();
        List<BaseEvent> events =
        [
            new RunStartedEvent { ThreadId = "thread1", RunId = "run1" },
            new TextMessageContentEvent { MessageId = "msg1", Delta = "Hello" }
        ];

        async IAsyncEnumerable<BaseEvent> GetEventsWithCancellationAsync()
        {
            foreach (BaseEvent evt in events)
            {
                yield return evt;
                await Task.Delay(10);
            }
        }

        ILogger<AGUIServerSentEventsResult> logger = NullLogger<AGUIServerSentEventsResult>.Instance;
        AGUIServerSentEventsResult result = new(GetEventsWithCancellationAsync(), logger);
        DefaultHttpContext httpContext = new();
        httpContext.Response.Body = new MemoryStream();
        httpContext.RequestAborted = cts.Token;

        // Act
        cts.Cancel();

        // Assert
        await Assert.ThrowsAnyAsync<OperationCanceledException>(() => result.ExecuteAsync(httpContext));
    }

    [Fact]
    public async Task ExecuteAsync_WithNullHttpContext_ThrowsArgumentNullExceptionAsync()
    {
        // Arrange
        List<BaseEvent> events = [];
        ILogger<AGUIServerSentEventsResult> logger = NullLogger<AGUIServerSentEventsResult>.Instance;
        AGUIServerSentEventsResult result = new(events.ToAsyncEnumerableAsync(), logger);

        // Act & Assert
        await Assert.ThrowsAsync<ArgumentNullException>(() => result.ExecuteAsync(null!));
    }
}
