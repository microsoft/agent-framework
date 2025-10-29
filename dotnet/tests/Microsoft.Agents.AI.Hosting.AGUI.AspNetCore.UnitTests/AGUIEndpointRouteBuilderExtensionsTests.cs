// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Hosting.AGUI.AspNetCore.Shared;
using Microsoft.AspNetCore.Builder;
using Microsoft.AspNetCore.Http;
using Microsoft.AspNetCore.Routing;
using Microsoft.Extensions.AI;
using Moq;

namespace Microsoft.Agents.AI.Hosting.AGUI.AspNetCore.UnitTests;

/// <summary>
/// Unit tests for the <see cref="AGUIEndpointRouteBuilderExtensions"/> class.
/// </summary>
public sealed class AGUIEndpointRouteBuilderExtensionsTests
{
    [Fact]
    public void MapAGUIAgent_MapsEndpoint_AtSpecifiedPattern()
    {
        // Arrange
        Mock<IEndpointRouteBuilder> endpointsMock = new();
        Mock<IServiceProvider> serviceProviderMock = new();
        Mock<IEndpointRouteBuilder> dataSourceBuilderMock = new();

        endpointsMock.Setup(e => e.ServiceProvider).Returns(serviceProviderMock.Object);
        endpointsMock.Setup(e => e.DataSources).Returns([]);

        const string Pattern = "/api/agent";
        static AIAgent factory(IEnumerable<ChatMessage> messages, IEnumerable<AITool> tools, IEnumerable<KeyValuePair<string, string>> context, JsonElement props) => new TestAgent();

        // Act
        IEndpointConventionBuilder? result = AGUIEndpointRouteBuilderExtensions.MapAGUIAgent(endpointsMock.Object, Pattern, factory);

        // Assert
        Assert.NotNull(result);
    }

    [Fact]
    public async Task MapAGUIAgent_WithNullOrInvalidInput_Returns400BadRequestAsync()
    {
        // Arrange
        DefaultHttpContext context = new();
        context.Request.Body = new MemoryStream(Encoding.UTF8.GetBytes("invalid json"));
        context.RequestAborted = CancellationToken.None;

        RequestDelegate handler = this.CreateRequestDelegate((messages, tools, ctx, props) => new TestAgent());

        // Act
        await handler(context);

        // Assert
        Assert.Equal(StatusCodes.Status400BadRequest, context.Response.StatusCode);
    }

    [Fact]
    public async Task MapAGUIAgent_InvokesAgentFactory_WithCorrectMessagesAndContextAsync()
    {
        // Arrange
        List<ChatMessage>? capturedMessages = null;
        IEnumerable<KeyValuePair<string, string>>? capturedContext = null;

        AIAgent factory(IEnumerable<ChatMessage> messages, IEnumerable<AITool> tools, IEnumerable<KeyValuePair<string, string>> context, JsonElement props)
        {
            capturedMessages = messages.ToList();
            capturedContext = context;
            return new TestAgent();
        }

        DefaultHttpContext httpContext = new();
        RunAgentInput input = new()
        {
            ThreadId = "thread1",
            RunId = "run1",
            Messages = [new AGUIMessage { Id = "m1", Role = AGUIRoles.User, Content = "Test" }],
            Context = new Dictionary<string, string> { ["key1"] = "value1" }
        };
        string json = JsonSerializer.Serialize(input, AGUIJsonSerializerContext.Default.RunAgentInput);
        httpContext.Request.Body = new MemoryStream(Encoding.UTF8.GetBytes(json));
        httpContext.Response.Body = new MemoryStream();

        RequestDelegate handler = this.CreateRequestDelegate(factory);

        // Act
        await handler(httpContext);

        // Assert
        Assert.NotNull(capturedMessages);
        Assert.Single(capturedMessages);
        Assert.Equal("Test", capturedMessages[0].Text);
        Assert.NotNull(capturedContext);
        Assert.Contains(capturedContext, kvp => kvp.Key == "key1" && kvp.Value == "value1");
    }

    [Fact]
    public async Task MapAGUIAgent_ReturnsSSEResponseStream_WithCorrectContentTypeAsync()
    {
        // Arrange
        DefaultHttpContext httpContext = new();
        RunAgentInput input = new()
        {
            ThreadId = "thread1",
            RunId = "run1",
            Messages = [new AGUIMessage { Id = "m1", Role = AGUIRoles.User, Content = "Test" }]
        };
        string json = JsonSerializer.Serialize(input, AGUIJsonSerializerContext.Default.RunAgentInput);
        httpContext.Request.Body = new MemoryStream(Encoding.UTF8.GetBytes(json));
        httpContext.Response.Body = new MemoryStream();

        RequestDelegate handler = this.CreateRequestDelegate((messages, tools, context, props) => new TestAgent());

        // Act
        await handler(httpContext);

        // Assert
        Assert.Equal("text/event-stream", httpContext.Response.ContentType);
    }

    [Fact]
    public async Task MapAGUIAgent_PassesCancellationToken_ToAgentExecutionAsync()
    {
        // Arrange
        CancellationTokenSource cts = new();
        cts.Cancel();

        DefaultHttpContext httpContext = new();
        RunAgentInput input = new()
        {
            ThreadId = "thread1",
            RunId = "run1",
            Messages = [new AGUIMessage { Id = "m1", Role = AGUIRoles.User, Content = "Test" }]
        };
        string json = JsonSerializer.Serialize(input, AGUIJsonSerializerContext.Default.RunAgentInput);
        httpContext.Request.Body = new MemoryStream(Encoding.UTF8.GetBytes(json));
        httpContext.Response.Body = new MemoryStream();
        httpContext.RequestAborted = cts.Token;

        RequestDelegate handler = this.CreateRequestDelegate((messages, tools, context, props) => new TestAgent());

        // Act & Assert
        await Assert.ThrowsAnyAsync<OperationCanceledException>(() => handler(httpContext));
    }

    [Fact]
    public async Task MapAGUIAgent_ConvertsInputMessages_ToChatMessagesBeforeFactoryAsync()
    {
        // Arrange
        List<ChatMessage>? capturedMessages = null;

        AIAgent factory(IEnumerable<ChatMessage> messages, IEnumerable<AITool> tools, IEnumerable<KeyValuePair<string, string>> context, JsonElement props)
        {
            capturedMessages = messages.ToList();
            return new TestAgent();
        }

        DefaultHttpContext httpContext = new();
        RunAgentInput input = new()
        {
            ThreadId = "thread1",
            RunId = "run1",
            Messages =
            [
                new AGUIMessage { Id = "m1", Role = AGUIRoles.User, Content = "First" },
                new AGUIMessage { Id = "m2", Role = AGUIRoles.Assistant, Content = "Second" }
            ]
        };
        string json = JsonSerializer.Serialize(input, AGUIJsonSerializerContext.Default.RunAgentInput);
        httpContext.Request.Body = new MemoryStream(Encoding.UTF8.GetBytes(json));
        httpContext.Response.Body = new MemoryStream();

        RequestDelegate handler = this.CreateRequestDelegate(factory);

        // Act
        await handler(httpContext);

        // Assert
        Assert.NotNull(capturedMessages);
        Assert.Equal(2, capturedMessages.Count);
        Assert.Equal(ChatRole.User, capturedMessages[0].Role);
        Assert.Equal("First", capturedMessages[0].Text);
        Assert.Equal(ChatRole.Assistant, capturedMessages[1].Role);
        Assert.Equal("Second", capturedMessages[1].Text);
    }

    private RequestDelegate CreateRequestDelegate(
        Func<IEnumerable<ChatMessage>, IEnumerable<AITool>, IEnumerable<KeyValuePair<string, string>>, JsonElement, AIAgent> factory)
    {
        return async context =>
        {
            CancellationToken cancellationToken = context.RequestAborted;

            RunAgentInput? input;
            try
            {
                input = await JsonSerializer.DeserializeAsync(
                    context.Request.Body,
                    AGUIJsonSerializerContext.Default.RunAgentInput,
                    cancellationToken).ConfigureAwait(false);
            }
            catch (JsonException)
            {
                context.Response.StatusCode = StatusCodes.Status400BadRequest;
                return;
            }

            if (input is null)
            {
                context.Response.StatusCode = StatusCodes.Status400BadRequest;
                return;
            }

            IEnumerable<ChatMessage> messages = input.Messages.AsChatMessages();
            IEnumerable<KeyValuePair<string, string>> contextValues = input.Context;
            JsonElement forwardedProps = input.ForwardedProperties;
            AIAgent agent = factory(messages, [], contextValues, forwardedProps);

            IAsyncEnumerable<BaseEvent> events = agent.RunStreamingAsync(
                messages,
                cancellationToken: cancellationToken)
                .AsAGUIEventStreamAsync(
                    input.ThreadId,
                    input.RunId,
                    cancellationToken);

            await new AGUIServerSentEventsResult(events).ExecuteAsync(context).ConfigureAwait(false);
        };
    }

    private sealed class TestInMemoryAgentThread : InMemoryAgentThread
    {
        public TestInMemoryAgentThread()
            : base()
        {
        }

        public TestInMemoryAgentThread(JsonElement serializedThreadState, JsonSerializerOptions? jsonSerializerOptions = null)
            : base(serializedThreadState, jsonSerializerOptions, null)
        {
        }
    }

    private sealed class TestAgent : AIAgent
    {
        public override string Id => "test-agent";

        public override string? Description => "Test agent";

        public override AgentThread GetNewThread() => new TestInMemoryAgentThread();

        public override AgentThread DeserializeThread(JsonElement serializedThread, JsonSerializerOptions? jsonSerializerOptions = null) =>
            new TestInMemoryAgentThread(serializedThread, jsonSerializerOptions);

        public override Task<AgentRunResponse> RunAsync(IEnumerable<ChatMessage> messages, AgentThread? thread = null, AgentRunOptions? options = null, CancellationToken cancellationToken = default)
        {
            throw new NotImplementedException();
        }

        public override async IAsyncEnumerable<AgentRunResponseUpdate> RunStreamingAsync(
            IEnumerable<ChatMessage> messages,
            AgentThread? thread = null,
            AgentRunOptions? options = null,
            [System.Runtime.CompilerServices.EnumeratorCancellation] CancellationToken cancellationToken = default)
        {
            await Task.CompletedTask;
            yield return new AgentRunResponseUpdate(new ChatResponseUpdate(ChatRole.Assistant, "Test response"));
        }
    }
}
