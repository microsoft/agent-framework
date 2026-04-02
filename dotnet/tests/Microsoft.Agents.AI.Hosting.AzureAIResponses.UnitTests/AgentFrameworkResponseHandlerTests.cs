// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Runtime.CompilerServices;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Azure.AI.AgentServer.Responses;
using Azure.AI.AgentServer.Responses.Models;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Logging.Abstractions;
using Moq;
using MeaiTextContent = Microsoft.Extensions.AI.TextContent;

namespace Microsoft.Agents.AI.Hosting.AzureAIResponses.UnitTests;

public class AgentFrameworkResponseHandlerTests
{
    [Fact]
    public async Task CreateAsync_WithDefaultAgent_ProducesStreamEvents()
    {
        // Arrange
        var agent = CreateTestAgent("Hello from the agent!");
        var services = new ServiceCollection();
        services.AddSingleton<AIAgent>(agent);
        services.AddSingleton<ILogger<AgentFrameworkResponseHandler>>(NullLogger<AgentFrameworkResponseHandler>.Instance);
        var sp = services.BuildServiceProvider();

        var handler = new AgentFrameworkResponseHandler(sp, NullLogger<AgentFrameworkResponseHandler>.Instance);

        var request = AzureAIAgentServerResponsesModelFactory.CreateResponse(model: "test");
        request.Input = BinaryData.FromObjectAsJson(new[]
        {
            new { type = "message", id = "msg_1", status = "completed", role = "user",
                  content = new[] { new { type = "input_text", text = "Hello" } } }
        });

        var mockContext = new Mock<ResponseContext>("resp_" + new string('0', 46)) { CallBase = true };
        mockContext.Setup(x => x.GetHistoryAsync(It.IsAny<CancellationToken>()))
            .ReturnsAsync(Array.Empty<OutputItem>());
        mockContext.Setup(x => x.GetInputItemsAsync(It.IsAny<CancellationToken>()))
            .ReturnsAsync(Array.Empty<OutputItem>());

        // Act
        var events = new List<ResponseStreamEvent>();
        await foreach (var evt in handler.CreateAsync(request, mockContext.Object, CancellationToken.None))
        {
            events.Add(evt);
        }

        // Assert
        Assert.True(events.Count >= 4, $"Expected at least 4 events, got {events.Count}");
        Assert.IsType<ResponseCreatedEvent>(events[0]);
        Assert.IsType<ResponseInProgressEvent>(events[1]);
    }

    [Fact]
    public async Task CreateAsync_WithKeyedAgent_ResolvesCorrectAgent()
    {
        // Arrange
        var agent = CreateTestAgent("Keyed agent response");
        var services = new ServiceCollection();
        services.AddKeyedSingleton<AIAgent>("my-agent", agent);
        var sp = services.BuildServiceProvider();

        var handler = new AgentFrameworkResponseHandler(sp, NullLogger<AgentFrameworkResponseHandler>.Instance);

        var request = AzureAIAgentServerResponsesModelFactory.CreateResponse(
            model: "test",
            agentReference: new AgentReference("my-agent"));
        request.Input = BinaryData.FromObjectAsJson(new[]
        {
            new { type = "message", id = "msg_1", status = "completed", role = "user",
                  content = new[] { new { type = "input_text", text = "Hello" } } }
        });

        var mockContext = new Mock<ResponseContext>("resp_" + new string('0', 46)) { CallBase = true };
        mockContext.Setup(x => x.GetHistoryAsync(It.IsAny<CancellationToken>()))
            .ReturnsAsync(Array.Empty<OutputItem>());
        mockContext.Setup(x => x.GetInputItemsAsync(It.IsAny<CancellationToken>()))
            .ReturnsAsync(Array.Empty<OutputItem>());

        // Act
        var events = new List<ResponseStreamEvent>();
        await foreach (var evt in handler.CreateAsync(request, mockContext.Object, CancellationToken.None))
        {
            events.Add(evt);
        }

        // Assert - should have produced events from the keyed agent
        Assert.True(events.Count >= 4);
        Assert.IsType<ResponseCreatedEvent>(events[0]);
    }

    [Fact]
    public async Task CreateAsync_NoAgentRegistered_ThrowsInvalidOperationException()
    {
        // Arrange
        var services = new ServiceCollection();
        var sp = services.BuildServiceProvider();

        var handler = new AgentFrameworkResponseHandler(sp, NullLogger<AgentFrameworkResponseHandler>.Instance);

        var request = AzureAIAgentServerResponsesModelFactory.CreateResponse(model: "test");
        request.Input = BinaryData.FromObjectAsJson(new[]
        {
            new { type = "message", id = "msg_1", status = "completed", role = "user",
                  content = new[] { new { type = "input_text", text = "Hello" } } }
        });

        var mockContext = new Mock<ResponseContext>("resp_" + new string('0', 46)) { CallBase = true };
        mockContext.Setup(x => x.GetHistoryAsync(It.IsAny<CancellationToken>()))
            .ReturnsAsync(Array.Empty<OutputItem>());
        mockContext.Setup(x => x.GetInputItemsAsync(It.IsAny<CancellationToken>()))
            .ReturnsAsync(Array.Empty<OutputItem>());

        // Act & Assert
        await Assert.ThrowsAsync<InvalidOperationException>(async () =>
        {
            await foreach (var _ in handler.CreateAsync(request, mockContext.Object, CancellationToken.None))
            {
            }
        });
    }

    [Fact]
    public void Constructor_NullServiceProvider_ThrowsArgumentNullException()
    {
        Assert.Throws<ArgumentNullException>(
            () => new AgentFrameworkResponseHandler(null!, NullLogger<AgentFrameworkResponseHandler>.Instance));
    }

    [Fact]
    public void Constructor_NullLogger_ThrowsArgumentNullException()
    {
        var sp = new ServiceCollection().BuildServiceProvider();
        Assert.Throws<ArgumentNullException>(
            () => new AgentFrameworkResponseHandler(sp, null!));
    }

    [Fact]
    public async Task CreateAsync_ResolvesAgentByModelField()
    {
        // Arrange
        var agent = CreateTestAgent("model agent");
        var services = new ServiceCollection();
        services.AddKeyedSingleton<AIAgent>("my-agent", agent);
        var sp = services.BuildServiceProvider();

        var handler = new AgentFrameworkResponseHandler(sp, NullLogger<AgentFrameworkResponseHandler>.Instance);

        var request = AzureAIAgentServerResponsesModelFactory.CreateResponse(model: "my-agent");
        request.Input = BinaryData.FromObjectAsJson(new[]
        {
            new { type = "message", id = "msg_1", status = "completed", role = "user",
                  content = new[] { new { type = "input_text", text = "Hello" } } }
        });

        var mockContext = new Mock<ResponseContext>("resp_" + new string('0', 46)) { CallBase = true };
        mockContext.Setup(x => x.GetHistoryAsync(It.IsAny<CancellationToken>()))
            .ReturnsAsync(Array.Empty<OutputItem>());
        mockContext.Setup(x => x.GetInputItemsAsync(It.IsAny<CancellationToken>()))
            .ReturnsAsync(Array.Empty<OutputItem>());

        // Act
        var events = new List<ResponseStreamEvent>();
        await foreach (var evt in handler.CreateAsync(request, mockContext.Object, CancellationToken.None))
        {
            events.Add(evt);
        }

        // Assert
        Assert.True(events.Count >= 4);
        Assert.IsType<ResponseCreatedEvent>(events[0]);
    }

    [Fact]
    public async Task CreateAsync_ResolvesAgentByEntityIdMetadata()
    {
        // Arrange
        var agent = CreateTestAgent("entity agent");
        var services = new ServiceCollection();
        services.AddKeyedSingleton<AIAgent>("entity-agent", agent);
        var sp = services.BuildServiceProvider();

        var handler = new AgentFrameworkResponseHandler(sp, NullLogger<AgentFrameworkResponseHandler>.Instance);

        var request = AzureAIAgentServerResponsesModelFactory.CreateResponse(model: "");
        var metadata = new Metadata();
        metadata.AdditionalProperties["entity_id"] = "entity-agent";
        request.Metadata = metadata;
        request.Input = BinaryData.FromObjectAsJson(new[]
        {
            new { type = "message", id = "msg_1", status = "completed", role = "user",
                  content = new[] { new { type = "input_text", text = "Hello" } } }
        });

        var mockContext = new Mock<ResponseContext>("resp_" + new string('0', 46)) { CallBase = true };
        mockContext.Setup(x => x.GetHistoryAsync(It.IsAny<CancellationToken>()))
            .ReturnsAsync(Array.Empty<OutputItem>());
        mockContext.Setup(x => x.GetInputItemsAsync(It.IsAny<CancellationToken>()))
            .ReturnsAsync(Array.Empty<OutputItem>());

        // Act
        var events = new List<ResponseStreamEvent>();
        await foreach (var evt in handler.CreateAsync(request, mockContext.Object, CancellationToken.None))
        {
            events.Add(evt);
        }

        // Assert
        Assert.True(events.Count >= 4);
        Assert.IsType<ResponseCreatedEvent>(events[0]);
    }

    [Fact]
    public async Task CreateAsync_NamedAgentNotFound_FallsBackToDefault()
    {
        // Arrange
        var agent = CreateTestAgent("default agent");
        var services = new ServiceCollection();
        services.AddSingleton<AIAgent>(agent);
        var sp = services.BuildServiceProvider();

        var handler = new AgentFrameworkResponseHandler(sp, NullLogger<AgentFrameworkResponseHandler>.Instance);

        var request = AzureAIAgentServerResponsesModelFactory.CreateResponse(
            model: "test",
            agentReference: new AgentReference("nonexistent-agent"));
        request.Input = BinaryData.FromObjectAsJson(new[]
        {
            new { type = "message", id = "msg_1", status = "completed", role = "user",
                  content = new[] { new { type = "input_text", text = "Hello" } } }
        });

        var mockContext = new Mock<ResponseContext>("resp_" + new string('0', 46)) { CallBase = true };
        mockContext.Setup(x => x.GetHistoryAsync(It.IsAny<CancellationToken>()))
            .ReturnsAsync(Array.Empty<OutputItem>());
        mockContext.Setup(x => x.GetInputItemsAsync(It.IsAny<CancellationToken>()))
            .ReturnsAsync(Array.Empty<OutputItem>());

        // Act
        var events = new List<ResponseStreamEvent>();
        await foreach (var evt in handler.CreateAsync(request, mockContext.Object, CancellationToken.None))
        {
            events.Add(evt);
        }

        // Assert
        Assert.True(events.Count >= 4);
        Assert.IsType<ResponseCreatedEvent>(events[0]);
    }

    [Fact]
    public async Task CreateAsync_NoAgentFound_ErrorMessageIncludesAgentName()
    {
        // Arrange
        var services = new ServiceCollection();
        var sp = services.BuildServiceProvider();

        var handler = new AgentFrameworkResponseHandler(sp, NullLogger<AgentFrameworkResponseHandler>.Instance);

        var request = AzureAIAgentServerResponsesModelFactory.CreateResponse(
            model: "test",
            agentReference: new AgentReference("missing-agent"));
        request.Input = BinaryData.FromObjectAsJson(new[]
        {
            new { type = "message", id = "msg_1", status = "completed", role = "user",
                  content = new[] { new { type = "input_text", text = "Hello" } } }
        });

        var mockContext = new Mock<ResponseContext>("resp_" + new string('0', 46)) { CallBase = true };
        mockContext.Setup(x => x.GetHistoryAsync(It.IsAny<CancellationToken>()))
            .ReturnsAsync(Array.Empty<OutputItem>());
        mockContext.Setup(x => x.GetInputItemsAsync(It.IsAny<CancellationToken>()))
            .ReturnsAsync(Array.Empty<OutputItem>());

        // Act & Assert
        var ex = await Assert.ThrowsAsync<InvalidOperationException>(async () =>
        {
            await foreach (var _ in handler.CreateAsync(request, mockContext.Object, CancellationToken.None))
            {
            }
        });

        Assert.Contains("missing-agent", ex.Message);
    }

    [Fact]
    public async Task CreateAsync_NoAgentNoName_ErrorMessageIsGeneric()
    {
        // Arrange
        var services = new ServiceCollection();
        var sp = services.BuildServiceProvider();

        var handler = new AgentFrameworkResponseHandler(sp, NullLogger<AgentFrameworkResponseHandler>.Instance);

        var request = AzureAIAgentServerResponsesModelFactory.CreateResponse(model: "");
        request.Input = BinaryData.FromObjectAsJson(new[]
        {
            new { type = "message", id = "msg_1", status = "completed", role = "user",
                  content = new[] { new { type = "input_text", text = "Hello" } } }
        });

        var mockContext = new Mock<ResponseContext>("resp_" + new string('0', 46)) { CallBase = true };
        mockContext.Setup(x => x.GetHistoryAsync(It.IsAny<CancellationToken>()))
            .ReturnsAsync(Array.Empty<OutputItem>());
        mockContext.Setup(x => x.GetInputItemsAsync(It.IsAny<CancellationToken>()))
            .ReturnsAsync(Array.Empty<OutputItem>());

        // Act & Assert
        var ex = await Assert.ThrowsAsync<InvalidOperationException>(async () =>
        {
            await foreach (var _ in handler.CreateAsync(request, mockContext.Object, CancellationToken.None))
            {
            }
        });

        Assert.Contains("No agent name specified", ex.Message);
    }

    [Fact]
    public async Task CreateAsync_AgentResolvedBeforeEmitCreated_ExceptionHasNoEvents()
    {
        // Arrange
        var services = new ServiceCollection();
        var sp = services.BuildServiceProvider();

        var handler = new AgentFrameworkResponseHandler(sp, NullLogger<AgentFrameworkResponseHandler>.Instance);

        var request = AzureAIAgentServerResponsesModelFactory.CreateResponse(model: "test");
        request.Input = BinaryData.FromObjectAsJson(new[]
        {
            new { type = "message", id = "msg_1", status = "completed", role = "user",
                  content = new[] { new { type = "input_text", text = "Hello" } } }
        });

        var mockContext = new Mock<ResponseContext>("resp_" + new string('0', 46)) { CallBase = true };
        mockContext.Setup(x => x.GetHistoryAsync(It.IsAny<CancellationToken>()))
            .ReturnsAsync(Array.Empty<OutputItem>());
        mockContext.Setup(x => x.GetInputItemsAsync(It.IsAny<CancellationToken>()))
            .ReturnsAsync(Array.Empty<OutputItem>());

        // Act
        var events = new List<ResponseStreamEvent>();
        bool threw = false;
        try
        {
            await foreach (var evt in handler.CreateAsync(request, mockContext.Object, CancellationToken.None))
            {
                events.Add(evt);
            }
        }
        catch (InvalidOperationException)
        {
            threw = true;
        }

        // Assert
        Assert.True(threw);
        Assert.Empty(events);
    }

    [Fact]
    public async Task CreateAsync_WithHistory_PrependsHistoryToMessages()
    {
        // Arrange
        var agent = new CapturingAgent();
        var services = new ServiceCollection();
        services.AddSingleton<AIAgent>(agent);
        var sp = services.BuildServiceProvider();

        var handler = new AgentFrameworkResponseHandler(sp, NullLogger<AgentFrameworkResponseHandler>.Instance);

        var request = AzureAIAgentServerResponsesModelFactory.CreateResponse(model: "test");
        request.Input = BinaryData.FromObjectAsJson(new[]
        {
            new { type = "message", id = "msg_1", status = "completed", role = "user",
                  content = new[] { new { type = "input_text", text = "Hello" } } }
        });

        var historyItem = new OutputItemMessage(
            id: "hist_1",
            role: MessageRole.Assistant,
            content: [new MessageContentOutputTextContent(
                "Previous response",
                Array.Empty<Annotation>(),
                Array.Empty<LogProb>())],
            status: MessageStatus.Completed);

        var mockContext = new Mock<ResponseContext>("resp_" + new string('0', 46)) { CallBase = true };
        mockContext.Setup(x => x.GetHistoryAsync(It.IsAny<CancellationToken>()))
            .ReturnsAsync(new OutputItem[] { historyItem });
        mockContext.Setup(x => x.GetInputItemsAsync(It.IsAny<CancellationToken>()))
            .ReturnsAsync(Array.Empty<OutputItem>());

        // Act
        var events = new List<ResponseStreamEvent>();
        await foreach (var evt in handler.CreateAsync(request, mockContext.Object, CancellationToken.None))
        {
            events.Add(evt);
        }

        // Assert
        Assert.NotNull(agent.CapturedMessages);
        var messages = agent.CapturedMessages.ToList();
        Assert.True(messages.Count >= 2);
        Assert.Equal(ChatRole.Assistant, messages[0].Role);
    }

    [Fact]
    public async Task CreateAsync_WithInputItems_UsesResolvedInputItems()
    {
        // Arrange
        var agent = new CapturingAgent();
        var services = new ServiceCollection();
        services.AddSingleton<AIAgent>(agent);
        var sp = services.BuildServiceProvider();

        var handler = new AgentFrameworkResponseHandler(sp, NullLogger<AgentFrameworkResponseHandler>.Instance);

        var request = AzureAIAgentServerResponsesModelFactory.CreateResponse(model: "test");
        request.Input = BinaryData.FromObjectAsJson(new[]
        {
            new { type = "message", id = "msg_1", status = "completed", role = "user",
                  content = new[] { new { type = "input_text", text = "Raw input" } } }
        });

        var inputItem = new OutputItemMessage(
            id: "input_1",
            role: MessageRole.Assistant,
            content: [new MessageContentOutputTextContent(
                "Resolved input",
                Array.Empty<Annotation>(),
                Array.Empty<LogProb>())],
            status: MessageStatus.Completed);

        var mockContext = new Mock<ResponseContext>("resp_" + new string('0', 46)) { CallBase = true };
        mockContext.Setup(x => x.GetHistoryAsync(It.IsAny<CancellationToken>()))
            .ReturnsAsync(Array.Empty<OutputItem>());
        mockContext.Setup(x => x.GetInputItemsAsync(It.IsAny<CancellationToken>()))
            .ReturnsAsync(new OutputItem[] { inputItem });

        // Act
        var events = new List<ResponseStreamEvent>();
        await foreach (var evt in handler.CreateAsync(request, mockContext.Object, CancellationToken.None))
        {
            events.Add(evt);
        }

        // Assert
        Assert.NotNull(agent.CapturedMessages);
        var messages = agent.CapturedMessages.ToList();
        Assert.Single(messages);
        Assert.Equal(ChatRole.Assistant, messages[0].Role);
    }

    [Fact]
    public async Task CreateAsync_NoInputItems_FallsBackToRawRequestInput()
    {
        // Arrange
        var agent = new CapturingAgent();
        var services = new ServiceCollection();
        services.AddSingleton<AIAgent>(agent);
        var sp = services.BuildServiceProvider();

        var handler = new AgentFrameworkResponseHandler(sp, NullLogger<AgentFrameworkResponseHandler>.Instance);

        var request = AzureAIAgentServerResponsesModelFactory.CreateResponse(model: "test");
        request.Input = BinaryData.FromObjectAsJson(new[]
        {
            new { type = "message", id = "msg_1", status = "completed", role = "user",
                  content = new[] { new { type = "input_text", text = "Raw input" } } }
        });

        var mockContext = new Mock<ResponseContext>("resp_" + new string('0', 46)) { CallBase = true };
        mockContext.Setup(x => x.GetHistoryAsync(It.IsAny<CancellationToken>()))
            .ReturnsAsync(Array.Empty<OutputItem>());
        mockContext.Setup(x => x.GetInputItemsAsync(It.IsAny<CancellationToken>()))
            .ReturnsAsync(Array.Empty<OutputItem>());

        // Act
        var events = new List<ResponseStreamEvent>();
        await foreach (var evt in handler.CreateAsync(request, mockContext.Object, CancellationToken.None))
        {
            events.Add(evt);
        }

        // Assert
        Assert.NotNull(agent.CapturedMessages);
        var messages = agent.CapturedMessages.ToList();
        Assert.Single(messages);
        Assert.Equal(ChatRole.User, messages[0].Role);
    }

    [Fact]
    public async Task CreateAsync_PassesInstructionsToAgent()
    {
        // Arrange
        var agent = new CapturingAgent();
        var services = new ServiceCollection();
        services.AddSingleton<AIAgent>(agent);
        var sp = services.BuildServiceProvider();

        var handler = new AgentFrameworkResponseHandler(sp, NullLogger<AgentFrameworkResponseHandler>.Instance);

        var request = AzureAIAgentServerResponsesModelFactory.CreateResponse(
            model: "test",
            instructions: "You are a helpful assistant.");
        request.Input = BinaryData.FromObjectAsJson(new[]
        {
            new { type = "message", id = "msg_1", status = "completed", role = "user",
                  content = new[] { new { type = "input_text", text = "Hello" } } }
        });

        var mockContext = new Mock<ResponseContext>("resp_" + new string('0', 46)) { CallBase = true };
        mockContext.Setup(x => x.GetHistoryAsync(It.IsAny<CancellationToken>()))
            .ReturnsAsync(Array.Empty<OutputItem>());
        mockContext.Setup(x => x.GetInputItemsAsync(It.IsAny<CancellationToken>()))
            .ReturnsAsync(Array.Empty<OutputItem>());

        // Act
        var events = new List<ResponseStreamEvent>();
        await foreach (var evt in handler.CreateAsync(request, mockContext.Object, CancellationToken.None))
        {
            events.Add(evt);
        }

        // Assert
        Assert.NotNull(agent.CapturedOptions);
        var chatClientOptions = Assert.IsType<ChatClientAgentRunOptions>(agent.CapturedOptions);
        Assert.Equal("You are a helpful assistant.", chatClientOptions.ChatOptions?.Instructions);
    }

    [Fact]
    public async Task CreateAsync_AgentThrows_ExceptionPropagates()
    {
        // Arrange
        var agent = new ThrowingAgent(new InvalidOperationException("Agent crashed"));
        var services = new ServiceCollection();
        services.AddSingleton<AIAgent>(agent);
        var sp = services.BuildServiceProvider();

        var handler = new AgentFrameworkResponseHandler(sp, NullLogger<AgentFrameworkResponseHandler>.Instance);

        var request = AzureAIAgentServerResponsesModelFactory.CreateResponse(model: "test");
        request.Input = BinaryData.FromObjectAsJson(new[]
        {
            new { type = "message", id = "msg_1", status = "completed", role = "user",
                  content = new[] { new { type = "input_text", text = "Hello" } } }
        });

        var mockContext = new Mock<ResponseContext>("resp_" + new string('0', 46)) { CallBase = true };
        mockContext.Setup(x => x.GetHistoryAsync(It.IsAny<CancellationToken>()))
            .ReturnsAsync(Array.Empty<OutputItem>());
        mockContext.Setup(x => x.GetInputItemsAsync(It.IsAny<CancellationToken>()))
            .ReturnsAsync(Array.Empty<OutputItem>());

        // Act & Assert
        await Assert.ThrowsAsync<InvalidOperationException>(async () =>
        {
            await foreach (var _ in handler.CreateAsync(request, mockContext.Object, CancellationToken.None))
            {
            }
        });
    }

    [Fact]
    public async Task CreateAsync_MultipleKeyedAgents_ResolvesCorrectOne()
    {
        // Arrange
        var agent1 = CreateTestAgent("Agent 1 response");
        var agent2 = CreateTestAgent("Agent 2 response");
        var services = new ServiceCollection();
        services.AddKeyedSingleton<AIAgent>("agent-1", agent1);
        services.AddKeyedSingleton<AIAgent>("agent-2", agent2);
        var sp = services.BuildServiceProvider();

        var handler = new AgentFrameworkResponseHandler(sp, NullLogger<AgentFrameworkResponseHandler>.Instance);

        var request = AzureAIAgentServerResponsesModelFactory.CreateResponse(
            model: "test",
            agentReference: new AgentReference("agent-2"));
        request.Input = BinaryData.FromObjectAsJson(new[]
        {
            new { type = "message", id = "msg_1", status = "completed", role = "user",
                  content = new[] { new { type = "input_text", text = "Hello" } } }
        });

        var mockContext = new Mock<ResponseContext>("resp_" + new string('0', 46)) { CallBase = true };
        mockContext.Setup(x => x.GetHistoryAsync(It.IsAny<CancellationToken>()))
            .ReturnsAsync(Array.Empty<OutputItem>());
        mockContext.Setup(x => x.GetInputItemsAsync(It.IsAny<CancellationToken>()))
            .ReturnsAsync(Array.Empty<OutputItem>());

        // Act
        var events = new List<ResponseStreamEvent>();
        await foreach (var evt in handler.CreateAsync(request, mockContext.Object, CancellationToken.None))
        {
            events.Add(evt);
        }

        // Assert
        Assert.True(events.Count >= 4);
        Assert.IsType<ResponseCreatedEvent>(events[0]);
    }

    [Fact]
    public async Task CreateAsync_CancellationDuringExecution_PropagatesOperationCanceledException()
    {
        // Arrange
        var agent = new CancellationCheckingAgent();
        var services = new ServiceCollection();
        services.AddSingleton<AIAgent>(agent);
        var sp = services.BuildServiceProvider();

        var handler = new AgentFrameworkResponseHandler(sp, NullLogger<AgentFrameworkResponseHandler>.Instance);

        var request = AzureAIAgentServerResponsesModelFactory.CreateResponse(model: "test");
        request.Input = BinaryData.FromObjectAsJson(new[]
        {
            new { type = "message", id = "msg_1", status = "completed", role = "user",
                  content = new[] { new { type = "input_text", text = "Hello" } } }
        });

        var mockContext = new Mock<ResponseContext>("resp_" + new string('0', 46)) { CallBase = true };
        mockContext.Setup(x => x.GetHistoryAsync(It.IsAny<CancellationToken>()))
            .ReturnsAsync(Array.Empty<OutputItem>());
        mockContext.Setup(x => x.GetInputItemsAsync(It.IsAny<CancellationToken>()))
            .ReturnsAsync(Array.Empty<OutputItem>());

        using var cts = new CancellationTokenSource();
        cts.Cancel();

        // Act & Assert
        await Assert.ThrowsAsync<OperationCanceledException>(async () =>
        {
            await foreach (var _ in handler.CreateAsync(request, mockContext.Object, cts.Token))
            {
            }
        });
    }

    private static TestAgent CreateTestAgent(string responseText)
    {
        return new TestAgent(responseText);
    }

    private static async IAsyncEnumerable<AgentResponseUpdate> ToAsyncEnumerableAsync(params AgentResponseUpdate[] items)
    {
        foreach (var item in items)
        {
            yield return item;
        }

        await Task.CompletedTask;
    }

    private sealed class TestAgent(string responseText) : AIAgent
    {
        protected override IAsyncEnumerable<AgentResponseUpdate> RunCoreStreamingAsync(
            IEnumerable<ChatMessage> messages,
            AgentSession? session,
            AgentRunOptions? options,
            CancellationToken cancellationToken = default) =>
            ToAsyncEnumerableAsync(new AgentResponseUpdate
            {
                MessageId = "resp_msg_1",
                Contents = [new MeaiTextContent(responseText)]
            });

        protected override Task<AgentResponse> RunCoreAsync(
            IEnumerable<ChatMessage> messages,
            AgentSession? session,
            AgentRunOptions? options,
            CancellationToken cancellationToken = default) =>
            throw new NotImplementedException();

        protected override ValueTask<AgentSession> CreateSessionCoreAsync(
            CancellationToken cancellationToken = default) =>
            throw new NotImplementedException();

        protected override ValueTask<JsonElement> SerializeSessionCoreAsync(
            AgentSession session,
            JsonSerializerOptions? jsonSerializerOptions,
            CancellationToken cancellationToken = default) =>
            throw new NotImplementedException();

        protected override ValueTask<AgentSession> DeserializeSessionCoreAsync(
            JsonElement serializedState,
            JsonSerializerOptions? jsonSerializerOptions,
            CancellationToken cancellationToken = default) =>
            throw new NotImplementedException();
    }

    private sealed class ThrowingAgent(Exception exception) : AIAgent
    {
        protected override IAsyncEnumerable<AgentResponseUpdate> RunCoreStreamingAsync(
            IEnumerable<ChatMessage> messages,
            AgentSession? session,
            AgentRunOptions? options,
            CancellationToken cancellationToken = default) =>
            throw exception;

        protected override Task<AgentResponse> RunCoreAsync(
            IEnumerable<ChatMessage> messages,
            AgentSession? session,
            AgentRunOptions? options,
            CancellationToken cancellationToken = default) =>
            throw new NotImplementedException();

        protected override ValueTask<AgentSession> CreateSessionCoreAsync(
            CancellationToken cancellationToken = default) =>
            throw new NotImplementedException();

        protected override ValueTask<JsonElement> SerializeSessionCoreAsync(
            AgentSession session,
            JsonSerializerOptions? jsonSerializerOptions,
            CancellationToken cancellationToken = default) =>
            throw new NotImplementedException();

        protected override ValueTask<AgentSession> DeserializeSessionCoreAsync(
            JsonElement serializedState,
            JsonSerializerOptions? jsonSerializerOptions,
            CancellationToken cancellationToken = default) =>
            throw new NotImplementedException();
    }

    private sealed class CapturingAgent : AIAgent
    {
        public IEnumerable<ChatMessage>? CapturedMessages { get; private set; }
        public AgentRunOptions? CapturedOptions { get; private set; }

        protected override IAsyncEnumerable<AgentResponseUpdate> RunCoreStreamingAsync(
            IEnumerable<ChatMessage> messages,
            AgentSession? session,
            AgentRunOptions? options,
            CancellationToken cancellationToken = default)
        {
            this.CapturedMessages = messages.ToList();
            this.CapturedOptions = options;
            return ToAsyncEnumerableAsync(new AgentResponseUpdate
            {
                MessageId = "resp_msg_1",
                Contents = [new MeaiTextContent("captured")]
            });
        }

        protected override Task<AgentResponse> RunCoreAsync(
            IEnumerable<ChatMessage> messages,
            AgentSession? session,
            AgentRunOptions? options,
            CancellationToken cancellationToken = default) =>
            throw new NotImplementedException();

        protected override ValueTask<AgentSession> CreateSessionCoreAsync(
            CancellationToken cancellationToken = default) =>
            throw new NotImplementedException();

        protected override ValueTask<JsonElement> SerializeSessionCoreAsync(
            AgentSession session,
            JsonSerializerOptions? jsonSerializerOptions,
            CancellationToken cancellationToken = default) =>
            throw new NotImplementedException();

        protected override ValueTask<AgentSession> DeserializeSessionCoreAsync(
            JsonElement serializedState,
            JsonSerializerOptions? jsonSerializerOptions,
            CancellationToken cancellationToken = default) =>
            throw new NotImplementedException();
    }

    private sealed class CancellationCheckingAgent : AIAgent
    {
        protected override async IAsyncEnumerable<AgentResponseUpdate> RunCoreStreamingAsync(
            IEnumerable<ChatMessage> messages,
            AgentSession? session,
            AgentRunOptions? options,
            [EnumeratorCancellation] CancellationToken cancellationToken = default)
        {
            cancellationToken.ThrowIfCancellationRequested();
            yield return new AgentResponseUpdate { Contents = [new MeaiTextContent("test")] };
            await Task.CompletedTask;
        }

        protected override Task<AgentResponse> RunCoreAsync(
            IEnumerable<ChatMessage> messages,
            AgentSession? session,
            AgentRunOptions? options,
            CancellationToken cancellationToken = default) =>
            throw new NotImplementedException();

        protected override ValueTask<AgentSession> CreateSessionCoreAsync(
            CancellationToken cancellationToken = default) =>
            throw new NotImplementedException();

        protected override ValueTask<JsonElement> SerializeSessionCoreAsync(
            AgentSession session,
            JsonSerializerOptions? jsonSerializerOptions,
            CancellationToken cancellationToken = default) =>
            throw new NotImplementedException();

        protected override ValueTask<AgentSession> DeserializeSessionCoreAsync(
            JsonElement serializedState,
            JsonSerializerOptions? jsonSerializerOptions,
            CancellationToken cancellationToken = default) =>
            throw new NotImplementedException();
    }
}
