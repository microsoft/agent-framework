// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Net;
using System.Net.Http;
using System.Net.ServerSentEvents;
using System.Text;
using System.Text.Encodings.Web;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using A2A;

namespace Microsoft.Extensions.AI.Agents.A2A.UnitTests;

/// <summary>
/// Unit tests for the <see cref="A2AAgent"/> class.
/// </summary>
public sealed class A2AAgentTests : IDisposable
{
    private readonly HttpClient _httpClient;
    private readonly A2AClientHttpMessageHandlerStub _handler;
    private readonly A2AClient _a2aClient;
    private readonly A2AAgent _agent;

    public A2AAgentTests()
    {
        this._handler = new A2AClientHttpMessageHandlerStub();
        this._httpClient = new HttpClient(this._handler, false);
        this._a2aClient = new A2AClient(new Uri("http://test-endpoint"), this._httpClient);
        this._agent = new A2AAgent(this._a2aClient);
    }

    [Fact]
    public void Constructor_WithAllParameters_InitializesPropertiesCorrectly()
    {
        // Arrange
        const string TestId = "test-id";
        const string TestName = "test-name";
        const string TestDescription = "test-description";
        const string TestDisplayName = "test-display-name";

        // Act
        var agent = new A2AAgent(this._a2aClient, TestId, TestName, TestDescription, TestDisplayName);

        // Assert
        Assert.Equal(TestId, agent.Id);
        Assert.Equal(TestName, agent.Name);
        Assert.Equal(TestDescription, agent.Description);
        Assert.Equal(TestDisplayName, agent.DisplayName);
    }

    [Fact]
    public void Constructor_WithNullA2AClient_ThrowsArgumentNullException() =>
        // Act & Assert
        Assert.Throws<ArgumentNullException>(() => new A2AAgent(null!));

    [Fact]
    public void Constructor_WithDefaultParameters_UsesBaseProperties()
    {
        // Act
        var agent = new A2AAgent(this._a2aClient);

        // Assert
        Assert.NotNull(agent.Id);
        Assert.NotEmpty(agent.Id);
        Assert.Null(agent.Name);
        Assert.Null(agent.Description);
        Assert.Equal(agent.Id, agent.DisplayName);
    }

    [Fact]
    public async Task RunAsync_NonUserRoleMessages_ThrowsArgumentExceptionAsync()
    {
        // Arrange
        var inputMessages = new List<ChatMessage>
        {
            new(ChatRole.Assistant, "I am an assistant message"),
            new(ChatRole.User, "Valid user message")
        };

        // Act & Assert
        await Assert.ThrowsAsync<ArgumentException>(() => this._agent.RunAsync(inputMessages));
    }

    [Fact]
    public async Task RunAsync_WithValidUserMessage_RunsSuccessfullyAsync()
    {
        // Arrange
        this._handler.ResponseToReturn = new Message
        {
            MessageId = "response-123",
            Role = MessageRole.Agent,
            Parts =
            [
                new TextPart { Text = "Hello! How can I help you today?" }
            ]
        };

        var inputMessages = new List<ChatMessage>
        {
            new(ChatRole.User, "Hello, world!")
        };

        // Act
        var result = await this._agent.RunAsync(inputMessages);

        // Assert input message sent to A2AClient
        var inputMessage = this._handler.CapturedMessageSendParams?.Message;
        Assert.NotNull(inputMessage);
        Assert.Single(inputMessage.Parts);
        Assert.Equal(MessageRole.User, inputMessage.Role);
        Assert.Equal("Hello, world!", ((TextPart)inputMessage.Parts[0]).Text);

        // Assert response from A2AClient is converted correctly
        Assert.NotNull(result);
        Assert.Equal(this._agent.Id, result.AgentId);
        Assert.Equal("response-123", result.ResponseId);

        Assert.NotNull(result.RawRepresentation);
        Assert.IsType<Message>(result.RawRepresentation);
        Assert.Equal("response-123", ((Message)result.RawRepresentation).MessageId);

        Assert.Single(result.Messages);
        Assert.Equal(ChatRole.Assistant, result.Messages[0].Role);
        Assert.Equal("Hello! How can I help you today?", result.Messages[0].Text);
    }

    [Fact]
    public async Task RunAsync_WithNewThread_UpdatesThreadConversationIdAsync()
    {
        // Arrange
        this._handler.ResponseToReturn = new Message
        {
            MessageId = "response-123",
            Role = MessageRole.Agent,
            Parts =
            [
                new TextPart { Text = "Response" }
            ],
            ContextId = "new-context-id"
        };

        var inputMessages = new List<ChatMessage>
        {
            new(ChatRole.User, "Test message")
        };

        var thread = this._agent.GetNewThread();

        // Act
        await this._agent.RunAsync(inputMessages, thread);

        // Assert
        Assert.IsType<A2AAgentThread>(thread);
        var a2aThread = (A2AAgentThread)thread;
        Assert.Equal("new-context-id", a2aThread.ContextId);
    }

    [Fact]
    public async Task RunAsync_WithExistingThread_SetConversationIdToMessageAsync()
    {
        // Arrange
        var inputMessages = new List<ChatMessage>
        {
            new(ChatRole.User, "Test message")
        };

        var thread = this._agent.GetNewThread();
        var a2aThread = (A2AAgentThread)thread;
        a2aThread.ContextId = "existing-context-id";

        // Act
        await this._agent.RunAsync(inputMessages, thread);

        // Assert
        var message = this._handler.CapturedMessageSendParams?.Message;
        Assert.NotNull(message);
        Assert.Equal("existing-context-id", message.ContextId);
    }

    [Fact]
    public async Task RunAsync_WithThreadHavingDifferentContextId_ThrowsInvalidOperationExceptionAsync()
    {
        // Arrange
        var inputMessages = new List<ChatMessage>
        {
            new(ChatRole.User, "Test message")
        };

        this._handler.ResponseToReturn = new Message
        {
            MessageId = "response-123",
            Role = MessageRole.Agent,
            Parts =
            [
                new TextPart { Text = "Response" }
            ],
            ContextId = "different-context"
        };

        var thread = this._agent.GetNewThread();
        var a2aThread = (A2AAgentThread)thread;
        a2aThread.ContextId = "existing-context-id";

        // Act & Assert
        await Assert.ThrowsAsync<InvalidOperationException>(() => this._agent.RunAsync(inputMessages, thread));
    }

    [Fact]
    public async Task RunStreamingAsync_WithValidUserMessage_YieldsAgentRunResponseUpdatesAsync()
    {
        // Arrange
        var inputMessages = new List<ChatMessage>
        {
            new(ChatRole.User, "Hello, streaming!")
        };

        this._handler.StreamingResponseToReturn = new Message()
        {
            MessageId = "stream-1",
            Role = MessageRole.Agent,
            Parts = [new TextPart { Text = "Hello" }],
            ContextId = "stream-context"
        };

        // Act
        var updates = new List<AgentRunResponseUpdate>();
        await foreach (var update in this._agent.RunStreamingAsync(inputMessages))
        {
            updates.Add(update);
        }

        // Assert
        Assert.Single(updates);

        // Assert input message sent to A2AClient
        var inputMessage = this._handler.CapturedMessageSendParams?.Message;
        Assert.NotNull(inputMessage);
        Assert.Single(inputMessage.Parts);
        Assert.Equal(MessageRole.User, inputMessage.Role);
        Assert.Equal("Hello, streaming!", ((TextPart)inputMessage.Parts[0]).Text);

        // Assert response from A2AClient is converted correctly
        Assert.Equal(ChatRole.Assistant, updates[0].Role);
        Assert.Equal("Hello", updates[0].Text);
        Assert.Equal("stream-1", updates[0].MessageId);
        Assert.Equal(this._agent.Id, updates[0].AgentId);
        Assert.Equal("stream-1", updates[0].ResponseId);

        Assert.NotNull(updates[0].RawRepresentation);
        Assert.IsType<Message>(updates[0].RawRepresentation);
        Assert.Equal("stream-1", ((Message)updates[0].RawRepresentation!).MessageId);
    }

    [Fact]
    public async Task RunStreamingAsync_WithThread_UpdatesThreadConversationIdAsync()
    {
        // Arrange
        var inputMessages = new List<ChatMessage>
        {
            new(ChatRole.User, "Test streaming")
        };

        this._handler.StreamingResponseToReturn = new Message()
        {
            MessageId = "stream-1",
            Role = MessageRole.Agent,
            Parts = [new TextPart { Text = "Response" }],
            ContextId = "new-stream-context"
        };

        var thread = this._agent.GetNewThread();

        // Act
        await foreach (var _ in this._agent.RunStreamingAsync(inputMessages, thread))
        {
            // Just iterate through to trigger the logic
        }

        // Assert
        var a2aThread = (A2AAgentThread)thread;
        Assert.Equal("new-stream-context", a2aThread.ContextId);
    }

    [Fact]
    public async Task RunStreamingAsync_WithExistingThread_SetConversationIdToMessageAsync()
    {
        // Arrange
        var inputMessages = new List<ChatMessage>
        {
            new(ChatRole.User, "Test streaming")
        };

        this._handler.StreamingResponseToReturn = new Message();

        var thread = this._agent.GetNewThread();
        var a2aThread = (A2AAgentThread)thread;
        a2aThread.ContextId = "existing-context-id";

        // Act
        await foreach (var _ in this._agent.RunStreamingAsync(inputMessages, thread))
        {
            // Just iterate through to trigger the logic
        }

        // Assert
        var message = this._handler.CapturedMessageSendParams?.Message;
        Assert.NotNull(message);
        Assert.Equal("existing-context-id", message.ContextId);
    }

    [Fact]
    public async Task RunStreamingAsync_WithThreadHavingDifferentContextId_ThrowsInvalidOperationExceptionAsync()
    {
        // Arrange
        var thread = this._agent.GetNewThread();
        var a2aThread = (A2AAgentThread)thread;
        a2aThread.ContextId = "existing-context-id";

        var inputMessages = new List<ChatMessage>
        {
            new(ChatRole.User, "Test streaming")
        };

        this._handler.StreamingResponseToReturn = new Message()
        {
            MessageId = "stream-1",
            Role = MessageRole.Agent,
            Parts = [new TextPart { Text = "Response" }],
            ContextId = "different-context"
        };

        // Act
        await Assert.ThrowsAsync<InvalidOperationException>(async () =>
        {
            await foreach (var update in this._agent.RunStreamingAsync(inputMessages, thread))
            {
            }
        });
    }

    [Fact]
    public async Task RunStreamingAsync_NonUserRoleMessages_ThrowsArgumentExceptionAsync()
    {
        // Arrange
        var inputMessages = new List<ChatMessage>
        {
            new(ChatRole.Assistant, "I am an assistant message")
        };

        // Act & Assert
        await Assert.ThrowsAsync<ArgumentException>(async () =>
        {
            await foreach (var update in this._agent.RunStreamingAsync(inputMessages))
            {
            }
        });
    }

    [Fact]
    public async Task RunAsync_WithHostedFileContent_ConvertsToFilePartAsync()
    {
        // Arrange
        var inputMessages = new List<ChatMessage>
        {
            new(ChatRole.User,
            [
                new TextContent("Check this file:"),
                new HostedFileContent("https://example.com/file.pdf")
            ])
        };

        // Act
        await this._agent.RunAsync(inputMessages);

        // Assert
        var message = this._handler.CapturedMessageSendParams?.Message;
        Assert.NotNull(message);
        Assert.Equal(2, message.Parts.Count);
        Assert.IsType<TextPart>(message.Parts[0]);
        Assert.Equal("Check this file:", ((TextPart)message.Parts[0]).Text);
        Assert.IsType<FilePart>(message.Parts[1]);
        Assert.Equal("https://example.com/file.pdf", ((FileWithUri)((FilePart)message.Parts[1]).File).Uri);
    }

    public void Dispose()
    {
        this._handler.Dispose();
        this._httpClient.Dispose();
    }
    internal sealed class A2AClientHttpMessageHandlerStub : HttpMessageHandler
    {
        public MessageSendParams? CapturedMessageSendParams { get; set; }

        public A2AEvent? ResponseToReturn { get; set; }

        public A2AEvent? StreamingResponseToReturn { get; set; }

        protected override async Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken cancellationToken)
        {
            // Capture the request content
#pragma warning disable CA2016 // Forward the 'CancellationToken' parameter to methods; overload doesn't exist downlevel
            var content = await request.Content!.ReadAsStringAsync();
#pragma warning restore CA2016

            var jsonRpcRequest = JsonSerializer.Deserialize<JsonRpcRequest>(content)!;

            this.CapturedMessageSendParams = jsonRpcRequest.Params?.Deserialize<MessageSendParams>();

            // Return the pre-configured non-streaming response
            if (this.ResponseToReturn is not null)
            {
                var jsonRpcResponse = JsonRpcResponse.CreateJsonRpcResponse("response-id", this.ResponseToReturn);

                return new HttpResponseMessage(HttpStatusCode.OK)
                {
                    Content = new StringContent(JsonSerializer.Serialize(jsonRpcResponse), Encoding.UTF8, "application/json")
                };
            }
            // Return the pre-configured streaming response
            else if (this.StreamingResponseToReturn is not null)
            {
                var stream = new MemoryStream();

                await SseFormatter.WriteAsync(
                    new SseItem<JsonRpcResponse>[]
                    {
                        new(JsonRpcResponse.CreateJsonRpcResponse("response-id", this.StreamingResponseToReturn!))
                    }.ToAsyncEnumerable(),
                    stream,
                    (item, writer) =>
                    {
                        using Utf8JsonWriter json = new(writer, new() { Encoder = JavaScriptEncoder.UnsafeRelaxedJsonEscaping });
                        JsonSerializer.Serialize(json, item.Data);
                    },
                    cancellationToken
                );

                stream.Position = 0;

                return new HttpResponseMessage(HttpStatusCode.OK)
                {
                    Content = new StreamContent(stream)
                    {
                        Headers = { { "Content-Type", "text/event-stream" } }
                    }
                };
            }
            else
            {
                var jsonRpcResponse = JsonRpcResponse.CreateJsonRpcResponse<A2AEvent>("response-id", new Message());

                return new HttpResponseMessage(HttpStatusCode.OK)
                {
                    Content = new StringContent(JsonSerializer.Serialize(jsonRpcResponse), Encoding.UTF8, "application/json")
                };
            }
        }
    }
}
