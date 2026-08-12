// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.IO;
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
using Microsoft.Extensions.Options;
using Moq;
using ChatCompletionOptions = OpenAI.Chat.ChatCompletionOptions;
using CreateResponseOptions = OpenAI.Responses.CreateResponseOptions;
using IncludedResponseProperty = OpenAI.Responses.IncludedResponseProperty;
using MeaiTextContent = Microsoft.Extensions.AI.TextContent;

namespace Microsoft.Agents.AI.Foundry.Hosting.UnitTests;

public class AgentFrameworkResponseHandlerTests
{
    [Fact]
    public async Task CreateAsync_WithDefaultAgent_ProducesStreamEventsAsync()
    {
        // Arrange
        var agent = CreateTestAgent("Hello from the agent!");
        var services = new ServiceCollection();
        services.AddSingleton<AgentSessionStore>(new InMemoryAgentSessionStore());
        services.AddSingleton<AIAgent>(agent);
        services.AddSingleton<ILogger<AgentFrameworkResponseHandler>>(NullLogger<AgentFrameworkResponseHandler>.Instance);
        services.AddSingleton<HostedSessionIsolationKeyProvider>(new FakeHostedSessionIsolationKeyProvider());
        var sp = services.BuildServiceProvider();

        var handler = new AgentFrameworkResponseHandler(sp, NullLogger<AgentFrameworkResponseHandler>.Instance);

        var request = new CreateResponse { Model = "test" };
        request.Input = BinaryData.FromObjectAsJson(new[]
        {
            new { type = "message", id = "msg_1", status = "completed", role = "user",
                  content = new[] { new { type = "input_text", text = "Hello" } } }
        });

        var mockContext = new Mock<ResponseContext>("resp_" + new string('0', 46)) { CallBase = true };
        mockContext.Setup(x => x.GetHistoryAsync(It.IsAny<CancellationToken>()))
            .ReturnsAsync(Array.Empty<OutputItem>());
        mockContext.Setup(x => x.GetInputItemsAsync(It.IsAny<bool>(), It.IsAny<CancellationToken>()))
            .ReturnsAsync(Array.Empty<Item>());

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
    public async Task CreateAsync_WithKeyedAgent_ResolvesCorrectAgentAsync()
    {
        // Arrange
        var agent = CreateTestAgent("Keyed agent response");
        var services = new ServiceCollection();
        services.AddSingleton<AgentSessionStore>(new InMemoryAgentSessionStore());
        services.AddKeyedSingleton<AIAgent>("my-agent", agent);
        services.AddSingleton<HostedSessionIsolationKeyProvider>(new FakeHostedSessionIsolationKeyProvider());
        var sp = services.BuildServiceProvider();

        var handler = new AgentFrameworkResponseHandler(sp, NullLogger<AgentFrameworkResponseHandler>.Instance);

        var request = new CreateResponse { Model = "test", AgentReference = new AgentReference("my-agent") };
        request.Input = BinaryData.FromObjectAsJson(new[]
        {
            new { type = "message", id = "msg_1", status = "completed", role = "user",
                  content = new[] { new { type = "input_text", text = "Hello" } } }
        });

        var mockContext = new Mock<ResponseContext>("resp_" + new string('0', 46)) { CallBase = true };
        mockContext.Setup(x => x.GetHistoryAsync(It.IsAny<CancellationToken>()))
            .ReturnsAsync(Array.Empty<OutputItem>());
        mockContext.Setup(x => x.GetInputItemsAsync(It.IsAny<bool>(), It.IsAny<CancellationToken>()))
            .ReturnsAsync(Array.Empty<Item>());

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
    public async Task CreateAsync_NoAgentRegistered_ThrowsInvalidOperationExceptionAsync()
    {
        // Arrange
        var services = new ServiceCollection();
        services.AddSingleton<AgentSessionStore>(new InMemoryAgentSessionStore());
        services.AddSingleton<HostedSessionIsolationKeyProvider>(new FakeHostedSessionIsolationKeyProvider());
        var sp = services.BuildServiceProvider();

        var handler = new AgentFrameworkResponseHandler(sp, NullLogger<AgentFrameworkResponseHandler>.Instance);

        var request = new CreateResponse { Model = "test" };
        request.Input = BinaryData.FromObjectAsJson(new[]
        {
            new { type = "message", id = "msg_1", status = "completed", role = "user",
                  content = new[] { new { type = "input_text", text = "Hello" } } }
        });

        var mockContext = new Mock<ResponseContext>("resp_" + new string('0', 46)) { CallBase = true };
        mockContext.Setup(x => x.GetHistoryAsync(It.IsAny<CancellationToken>()))
            .ReturnsAsync(Array.Empty<OutputItem>());
        mockContext.Setup(x => x.GetInputItemsAsync(It.IsAny<bool>(), It.IsAny<CancellationToken>()))
            .ReturnsAsync(Array.Empty<Item>());

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
    public async Task CreateAsync_ResolvesAgentByModelFieldAsync()
    {
        // Arrange
        var agent = CreateTestAgent("model agent");
        var services = new ServiceCollection();
        services.AddSingleton<AgentSessionStore>(new InMemoryAgentSessionStore());
        services.AddKeyedSingleton<AIAgent>("my-agent", agent);
        services.AddSingleton<HostedSessionIsolationKeyProvider>(new FakeHostedSessionIsolationKeyProvider());
        var sp = services.BuildServiceProvider();

        var handler = new AgentFrameworkResponseHandler(sp, NullLogger<AgentFrameworkResponseHandler>.Instance);

        var request = new CreateResponse { Model = "my-agent" };
        request.Input = BinaryData.FromObjectAsJson(new[]
        {
            new { type = "message", id = "msg_1", status = "completed", role = "user",
                  content = new[] { new { type = "input_text", text = "Hello" } } }
        });

        var mockContext = new Mock<ResponseContext>("resp_" + new string('0', 46)) { CallBase = true };
        mockContext.Setup(x => x.GetHistoryAsync(It.IsAny<CancellationToken>()))
            .ReturnsAsync(Array.Empty<OutputItem>());
        mockContext.Setup(x => x.GetInputItemsAsync(It.IsAny<bool>(), It.IsAny<CancellationToken>()))
            .ReturnsAsync(Array.Empty<Item>());

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
    public async Task CreateAsync_ResolvesAgentByEntityIdMetadataAsync()
    {
        // Arrange
        var agent = CreateTestAgent("entity agent");
        var services = new ServiceCollection();
        services.AddSingleton<AgentSessionStore>(new InMemoryAgentSessionStore());
        services.AddKeyedSingleton<AIAgent>("entity-agent", agent);
        services.AddSingleton<HostedSessionIsolationKeyProvider>(new FakeHostedSessionIsolationKeyProvider());
        var sp = services.BuildServiceProvider();

        var handler = new AgentFrameworkResponseHandler(sp, NullLogger<AgentFrameworkResponseHandler>.Instance);

        var request = new CreateResponse { Model = "" };
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
        mockContext.Setup(x => x.GetInputItemsAsync(It.IsAny<bool>(), It.IsAny<CancellationToken>()))
            .ReturnsAsync(Array.Empty<Item>());

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
    public async Task CreateAsync_NamedAgentNotFound_FallsBackToDefaultAsync()
    {
        // Arrange
        var agent = CreateTestAgent("default agent");
        var services = new ServiceCollection();
        services.AddSingleton<AgentSessionStore>(new InMemoryAgentSessionStore());
        services.AddSingleton<AIAgent>(agent);
        services.AddSingleton<HostedSessionIsolationKeyProvider>(new FakeHostedSessionIsolationKeyProvider());
        var sp = services.BuildServiceProvider();

        var handler = new AgentFrameworkResponseHandler(sp, NullLogger<AgentFrameworkResponseHandler>.Instance);

        var request = new CreateResponse { Model = "test", AgentReference = new AgentReference("nonexistent-agent") };
        request.Input = BinaryData.FromObjectAsJson(new[]
        {
            new { type = "message", id = "msg_1", status = "completed", role = "user",
                  content = new[] { new { type = "input_text", text = "Hello" } } }
        });

        var mockContext = new Mock<ResponseContext>("resp_" + new string('0', 46)) { CallBase = true };
        mockContext.Setup(x => x.GetHistoryAsync(It.IsAny<CancellationToken>()))
            .ReturnsAsync(Array.Empty<OutputItem>());
        mockContext.Setup(x => x.GetInputItemsAsync(It.IsAny<bool>(), It.IsAny<CancellationToken>()))
            .ReturnsAsync(Array.Empty<Item>());

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
    public async Task CreateAsync_NoAgentFound_ErrorMessageIncludesAgentNameAsync()
    {
        // Arrange
        var services = new ServiceCollection();
        services.AddSingleton<AgentSessionStore>(new InMemoryAgentSessionStore());
        services.AddSingleton<HostedSessionIsolationKeyProvider>(new FakeHostedSessionIsolationKeyProvider());
        var sp = services.BuildServiceProvider();

        var handler = new AgentFrameworkResponseHandler(sp, NullLogger<AgentFrameworkResponseHandler>.Instance);

        var request = new CreateResponse { Model = "test", AgentReference = new AgentReference("missing-agent") };
        request.Input = BinaryData.FromObjectAsJson(new[]
        {
            new { type = "message", id = "msg_1", status = "completed", role = "user",
                  content = new[] { new { type = "input_text", text = "Hello" } } }
        });

        var mockContext = new Mock<ResponseContext>("resp_" + new string('0', 46)) { CallBase = true };
        mockContext.Setup(x => x.GetHistoryAsync(It.IsAny<CancellationToken>()))
            .ReturnsAsync(Array.Empty<OutputItem>());
        mockContext.Setup(x => x.GetInputItemsAsync(It.IsAny<bool>(), It.IsAny<CancellationToken>()))
            .ReturnsAsync(Array.Empty<Item>());

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
    public async Task CreateAsync_NoAgentNoName_ErrorMessageIsGenericAsync()
    {
        // Arrange
        var services = new ServiceCollection();
        services.AddSingleton<AgentSessionStore>(new InMemoryAgentSessionStore());
        services.AddSingleton<HostedSessionIsolationKeyProvider>(new FakeHostedSessionIsolationKeyProvider());
        var sp = services.BuildServiceProvider();

        var handler = new AgentFrameworkResponseHandler(sp, NullLogger<AgentFrameworkResponseHandler>.Instance);

        var request = new CreateResponse { Model = "" };
        request.Input = BinaryData.FromObjectAsJson(new[]
        {
            new { type = "message", id = "msg_1", status = "completed", role = "user",
                  content = new[] { new { type = "input_text", text = "Hello" } } }
        });

        var mockContext = new Mock<ResponseContext>("resp_" + new string('0', 46)) { CallBase = true };
        mockContext.Setup(x => x.GetHistoryAsync(It.IsAny<CancellationToken>()))
            .ReturnsAsync(Array.Empty<OutputItem>());
        mockContext.Setup(x => x.GetInputItemsAsync(It.IsAny<bool>(), It.IsAny<CancellationToken>()))
            .ReturnsAsync(Array.Empty<Item>());

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
    public async Task CreateAsync_AgentResolvedBeforeEmitCreated_ExceptionHasNoEventsAsync()
    {
        // Arrange
        var services = new ServiceCollection();
        services.AddSingleton<AgentSessionStore>(new InMemoryAgentSessionStore());
        services.AddSingleton<HostedSessionIsolationKeyProvider>(new FakeHostedSessionIsolationKeyProvider());
        var sp = services.BuildServiceProvider();

        var handler = new AgentFrameworkResponseHandler(sp, NullLogger<AgentFrameworkResponseHandler>.Instance);

        var request = new CreateResponse { Model = "test" };
        request.Input = BinaryData.FromObjectAsJson(new[]
        {
            new { type = "message", id = "msg_1", status = "completed", role = "user",
                  content = new[] { new { type = "input_text", text = "Hello" } } }
        });

        var mockContext = new Mock<ResponseContext>("resp_" + new string('0', 46)) { CallBase = true };
        mockContext.Setup(x => x.GetHistoryAsync(It.IsAny<CancellationToken>()))
            .ReturnsAsync(Array.Empty<OutputItem>());
        mockContext.Setup(x => x.GetInputItemsAsync(It.IsAny<bool>(), It.IsAny<CancellationToken>()))
            .ReturnsAsync(Array.Empty<Item>());

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
    public async Task CreateAsync_WithHistory_LeavesTheNewInputAloneAsync()
    {
        // Arrange
        var agent = new CapturingAgent();
        var services = new ServiceCollection();
        services.AddSingleton<AgentSessionStore>(new InMemoryAgentSessionStore());
        services.AddSingleton<AIAgent>(agent);
        services.AddSingleton<HostedSessionIsolationKeyProvider>(new FakeHostedSessionIsolationKeyProvider());
        var sp = services.BuildServiceProvider();

        var handler = new AgentFrameworkResponseHandler(sp, NullLogger<AgentFrameworkResponseHandler>.Instance);

        var request = new CreateResponse { Model = "test" };
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
        mockContext.Setup(x => x.GetInputItemsAsync(It.IsAny<bool>(), It.IsAny<CancellationToken>()))
            .ReturnsAsync(Array.Empty<Item>());

        // Act
        var events = new List<ResponseStreamEvent>();
        await foreach (var evt in handler.CreateAsync(request, mockContext.Object, CancellationToken.None))
        {
            events.Add(evt);
        }

        // Assert
        // Assert: this agent supplies its own history, so only the new input reaches it.
        Assert.NotNull(agent.CapturedMessages);
        var messages = agent.CapturedMessages.ToList();
        Assert.Single(messages);
        Assert.Equal(ChatRole.User, messages[0].Role);
    }

    [Fact]
    public async Task CreateAsync_WithInputItems_UsesResolvedInputItemsAsync()
    {
        // Arrange
        var agent = new CapturingAgent();
        var services = new ServiceCollection();
        services.AddSingleton<AgentSessionStore>(new InMemoryAgentSessionStore());
        services.AddSingleton<AIAgent>(agent);
        services.AddSingleton<HostedSessionIsolationKeyProvider>(new FakeHostedSessionIsolationKeyProvider());
        var sp = services.BuildServiceProvider();

        var handler = new AgentFrameworkResponseHandler(sp, NullLogger<AgentFrameworkResponseHandler>.Instance);

        var request = new CreateResponse { Model = "test" };
        request.Input = BinaryData.FromObjectAsJson(new[]
        {
            new { type = "message", id = "msg_1", status = "completed", role = "user",
                  content = new[] { new { type = "input_text", text = "Raw input" } } }
        });

        var inputItem = new ItemMessage(
            MessageRole.Assistant,
            [new MessageContentInputTextContent("Resolved input")]);

        var mockContext = new Mock<ResponseContext>("resp_" + new string('0', 46)) { CallBase = true };
        mockContext.Setup(x => x.GetHistoryAsync(It.IsAny<CancellationToken>()))
            .ReturnsAsync(Array.Empty<OutputItem>());
        mockContext.Setup(x => x.GetInputItemsAsync(It.IsAny<bool>(), It.IsAny<CancellationToken>()))
            .ReturnsAsync(new Item[] { inputItem });

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
    public async Task CreateAsync_NoInputItems_FallsBackToRawRequestInputAsync()
    {
        // Arrange
        var agent = new CapturingAgent();
        var services = new ServiceCollection();
        services.AddSingleton<AgentSessionStore>(new InMemoryAgentSessionStore());
        services.AddSingleton<AIAgent>(agent);
        services.AddSingleton<HostedSessionIsolationKeyProvider>(new FakeHostedSessionIsolationKeyProvider());
        var sp = services.BuildServiceProvider();

        var handler = new AgentFrameworkResponseHandler(sp, NullLogger<AgentFrameworkResponseHandler>.Instance);

        var request = new CreateResponse { Model = "test" };
        request.Input = BinaryData.FromObjectAsJson(new[]
        {
            new { type = "message", id = "msg_1", status = "completed", role = "user",
                  content = new[] { new { type = "input_text", text = "Raw input" } } }
        });

        var mockContext = new Mock<ResponseContext>("resp_" + new string('0', 46)) { CallBase = true };
        mockContext.Setup(x => x.GetHistoryAsync(It.IsAny<CancellationToken>()))
            .ReturnsAsync(Array.Empty<OutputItem>());
        mockContext.Setup(x => x.GetInputItemsAsync(It.IsAny<bool>(), It.IsAny<CancellationToken>()))
            .ReturnsAsync(Array.Empty<Item>());

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
    public async Task CreateAsync_PassesInstructionsToAgentAsync()
    {
        // Arrange
        var agent = new CapturingAgent();
        var services = new ServiceCollection();
        services.AddSingleton<AgentSessionStore>(new InMemoryAgentSessionStore());
        services.AddSingleton<AIAgent>(agent);
        services.AddSingleton<HostedSessionIsolationKeyProvider>(new FakeHostedSessionIsolationKeyProvider());
        var sp = services.BuildServiceProvider();

        var handler = new AgentFrameworkResponseHandler(sp, NullLogger<AgentFrameworkResponseHandler>.Instance);

        var request = new CreateResponse
        {
            Model = "test",
            Instructions = "You are a helpful assistant.",
        };
        request.Input = BinaryData.FromObjectAsJson(new[]
        {
            new { type = "message", id = "msg_1", status = "completed", role = "user",
                  content = new[] { new { type = "input_text", text = "Hello" } } }
        });

        var mockContext = new Mock<ResponseContext>("resp_" + new string('0', 46)) { CallBase = true };
        mockContext.Setup(x => x.GetHistoryAsync(It.IsAny<CancellationToken>()))
            .ReturnsAsync(Array.Empty<OutputItem>());
        mockContext.Setup(x => x.GetInputItemsAsync(It.IsAny<bool>(), It.IsAny<CancellationToken>()))
            .ReturnsAsync(Array.Empty<Item>());

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
    public async Task CreateAsync_AgentThrows_EmitsFailedEventWithErrorMessageAsync()
    {
        // Arrange
        var agent = new ThrowingAgent(new InvalidOperationException("Agent crashed"));
        var services = new ServiceCollection();
        services.AddSingleton<AgentSessionStore>(new InMemoryAgentSessionStore());
        services.AddSingleton<AIAgent>(agent);
        services.AddSingleton<HostedSessionIsolationKeyProvider>(new FakeHostedSessionIsolationKeyProvider());
        var sp = services.BuildServiceProvider();

        var handler = new AgentFrameworkResponseHandler(sp, NullLogger<AgentFrameworkResponseHandler>.Instance);

        var request = new CreateResponse { Model = "test" };
        request.Input = BinaryData.FromObjectAsJson(new[]
        {
            new { type = "message", id = "msg_1", status = "completed", role = "user",
                  content = new[] { new { type = "input_text", text = "Hello" } } }
        });

        var mockContext = new Mock<ResponseContext>("resp_" + new string('0', 46)) { CallBase = true };
        mockContext.Setup(x => x.GetHistoryAsync(It.IsAny<CancellationToken>()))
            .ReturnsAsync(Array.Empty<OutputItem>());
        mockContext.Setup(x => x.GetInputItemsAsync(It.IsAny<bool>(), It.IsAny<CancellationToken>()))
            .ReturnsAsync(Array.Empty<Item>());

        // Act — collect all events
        var events = new List<ResponseStreamEvent>();
        await foreach (var evt in handler.CreateAsync(request, mockContext.Object, CancellationToken.None))
        {
            events.Add(evt);
        }

        // Assert — should contain created, in_progress, and failed (with real error message)
        Assert.Contains(events, e => e is ResponseCreatedEvent);
        Assert.Contains(events, e => e is ResponseInProgressEvent);
        var failedEvent = Assert.Single(events.OfType<ResponseFailedEvent>());
        Assert.Contains("Agent crashed", failedEvent.Response.Error.Message);
    }

    [Fact]
    public async Task CreateAsync_MultipleKeyedAgents_ResolvesCorrectOneAsync()
    {
        // Arrange
        var agent1 = CreateTestAgent("Agent 1 response");
        var agent2 = CreateTestAgent("Agent 2 response");
        var services = new ServiceCollection();
        services.AddSingleton<AgentSessionStore>(new InMemoryAgentSessionStore());
        services.AddKeyedSingleton<AIAgent>("agent-1", agent1);
        services.AddKeyedSingleton<AIAgent>("agent-2", agent2);
        services.AddSingleton<HostedSessionIsolationKeyProvider>(new FakeHostedSessionIsolationKeyProvider());
        var sp = services.BuildServiceProvider();

        var handler = new AgentFrameworkResponseHandler(sp, NullLogger<AgentFrameworkResponseHandler>.Instance);

        var request = new CreateResponse { Model = "test", AgentReference = new AgentReference("agent-2") };
        request.Input = BinaryData.FromObjectAsJson(new[]
        {
            new { type = "message", id = "msg_1", status = "completed", role = "user",
                  content = new[] { new { type = "input_text", text = "Hello" } } }
        });

        var mockContext = new Mock<ResponseContext>("resp_" + new string('0', 46)) { CallBase = true };
        mockContext.Setup(x => x.GetHistoryAsync(It.IsAny<CancellationToken>()))
            .ReturnsAsync(Array.Empty<OutputItem>());
        mockContext.Setup(x => x.GetInputItemsAsync(It.IsAny<bool>(), It.IsAny<CancellationToken>()))
            .ReturnsAsync(Array.Empty<Item>());

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
    public async Task CreateAsync_CancellationDuringExecution_PropagatesOperationCanceledExceptionAsync()
    {
        // Arrange
        var agent = new CancellationCheckingAgent();
        var services = new ServiceCollection();
        services.AddSingleton<AgentSessionStore>(new InMemoryAgentSessionStore());
        services.AddSingleton<AIAgent>(agent);
        services.AddSingleton<HostedSessionIsolationKeyProvider>(new FakeHostedSessionIsolationKeyProvider());
        var sp = services.BuildServiceProvider();

        var handler = new AgentFrameworkResponseHandler(sp, NullLogger<AgentFrameworkResponseHandler>.Instance);

        var request = new CreateResponse { Model = "test" };
        request.Input = BinaryData.FromObjectAsJson(new[]
        {
            new { type = "message", id = "msg_1", status = "completed", role = "user",
                  content = new[] { new { type = "input_text", text = "Hello" } } }
        });

        var mockContext = new Mock<ResponseContext>("resp_" + new string('0', 46)) { CallBase = true };
        mockContext.Setup(x => x.GetHistoryAsync(It.IsAny<CancellationToken>()))
            .ReturnsAsync(Array.Empty<OutputItem>());
        mockContext.Setup(x => x.GetInputItemsAsync(It.IsAny<bool>(), It.IsAny<CancellationToken>()))
            .ReturnsAsync(Array.Empty<Item>());

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

    [Fact]
    public async Task CreateAsync_DefaultAgent_IsAutoWrappedWithOpenTelemetryAsync()
    {
        // Arrange — register a plain (non-instrumented) agent
        var agent = CreateTestAgent("otel test response");
        var services = new ServiceCollection();
        services.AddSingleton<AgentSessionStore>(new InMemoryAgentSessionStore());
        services.AddSingleton<AIAgent>(agent);
        services.AddSingleton<HostedSessionIsolationKeyProvider>(new FakeHostedSessionIsolationKeyProvider());
        var sp = services.BuildServiceProvider();

        var handler = new AgentFrameworkResponseHandler(sp, NullLogger<AgentFrameworkResponseHandler>.Instance);

        var request = new CreateResponse { Model = "test" };
        request.Input = BinaryData.FromObjectAsJson(new[]
        {
            new { type = "message", id = "msg_1", status = "completed", role = "user",
                  content = new[] { new { type = "input_text", text = "Hello" } } }
        });

        var mockContext = new Mock<ResponseContext>("resp_" + new string('0', 46)) { CallBase = true };
        mockContext.Setup(x => x.GetHistoryAsync(It.IsAny<CancellationToken>()))
            .ReturnsAsync(Array.Empty<OutputItem>());
        mockContext.Setup(x => x.GetInputItemsAsync(It.IsAny<bool>(), It.IsAny<CancellationToken>()))
            .ReturnsAsync(Array.Empty<Item>());

        // Act — OTel wrapping must not break the stream
        var events = new List<ResponseStreamEvent>();
        await foreach (var evt in handler.CreateAsync(request, mockContext.Object, CancellationToken.None))
        {
            events.Add(evt);
        }

        // Assert — stream events are still produced correctly through the wrapper
        Assert.True(events.Count >= 4, $"Expected at least 4 events, got {events.Count}");
        Assert.IsType<ResponseCreatedEvent>(events[0]);
        Assert.IsType<ResponseInProgressEvent>(events[1]);
    }

    #region Resume detection

    [Fact]
    public async Task CreateAsync_FirstTurnOfAKnownConversation_StillReceivesTheServiceHistoryAsync()
    {
        // Arrange: the first turn this container serves for a conversation the service already holds
        // history for. Nothing has been persisted for it yet, so this is not a resume: the history has
        // to be handed to the agent, otherwise it answers knowing nothing of the conversation.
        var captured = new List<ChatMessage>();
        var agent = new ChatClientAgent(CreateCapturingChatClient(captured), new ChatClientAgentOptions { Name = "keeps-nothing" });
        var handler = BuildHandlerWith(agent, new FakeHostedSessionIsolationKeyProvider(), new InMemoryAgentSessionStore());
        var request = new CreateResponse { Model = "test" };
        request.Conversation = BinaryData.FromString("\"conv-known\"");
        request.Input = BinaryData.FromObjectAsJson(new[]
        {
            new { type = "message", id = "msg_1", status = "completed", role = "user",
                  content = new[] { new { type = "input_text", text = "new question" } } }
        });
        var ctx = new Mock<ResponseContext>("resp_" + new string('4', 46)) { CallBase = true };
        ctx.Setup(x => x.PlatformContext).Returns(new PlatformContext("alice", null));
        ctx.Setup(x => x.GetHistoryAsync(It.IsAny<CancellationToken>()))
           .ReturnsAsync([NewHistoryMessageItem("msg_hist_1", "earlier turn")]);
        ctx.Setup(x => x.GetInputItemsAsync(It.IsAny<bool>(), It.IsAny<CancellationToken>())).ReturnsAsync(Array.Empty<Item>());

        // Act
        await DrainEventsAsync(handler.CreateAsync(request, ctx.Object, CancellationToken.None));

        // Assert: whether this is a resume is answered by the session store, not by looking for state on
        // the session. The handler writes the caller's identity onto a session before this point, so a
        // freshly created session already carries state and reading that as "it has run before" made the
        // first turn of every conversation look like a resume, dropping its history. It only showed up
        // when hosted, because there is no identity to write locally.
        Assert.Contains(captured, m => m.Text.Contains("earlier turn", StringComparison.Ordinal));
    }

    [Fact]
    public async Task CreateAsync_SecondTurnOfAWorkflow_DoesNotReplayTheServiceHistoryAsync()
    {
        // Arrange: a hosted workflow, whose session carries the conversation in its own state, and a
        // first turn that persists it.
        const string ConversationId = "conv-resumed";
        var agent = new WorkflowLikeAgent();
        var store = new InMemoryAgentSessionStore();
        var handler = BuildHandlerWith(agent, new FakeHostedSessionIsolationKeyProvider(), store);
        await DrainEventsAsync(handler.CreateAsync(
            NewConversationTurn(ConversationId, "first question"),
            NewServingContext("resp_" + new string('5', 46), []),
            CancellationToken.None));

        // Act: a second turn of the same conversation, for which the service now reports history.
        await DrainEventsAsync(handler.CreateAsync(
            NewConversationTurn(ConversationId, "second question"),
            NewServingContext("resp_" + new string('6', 46), [NewHistoryMessageItem("msg_hist_1", "first question")]),
            CancellationToken.None));

        // Assert: a workflow takes everything handed to it as newly arrived input, and its session
        // already holds these turns, so handing them over again would re-drive work it has already done.
        Assert.NotNull(agent.CapturedMessages);
        Assert.DoesNotContain(agent.CapturedMessages!, m => m.Text.Contains("first question", StringComparison.Ordinal));
    }

    [Fact]
    public async Task CreateAsync_SecondTurnOfAnAgentThatKeepsNothing_StillReceivesTheServiceHistoryAsync()
    {
        // Arrange: an agent written outside this repo that runs no chat history provider and keeps
        // nothing in its session, with a first turn that persists one anyway.
        const string ConversationId = "conv-keeps-nothing";
        var captured = new List<ChatMessage>();
        var agent = new ChatClientAgent(CreateCapturingChatClient(captured), new ChatClientAgentOptions { Name = "keeps-nothing" });
        var store = new InMemoryAgentSessionStore();
        var handler = BuildHandlerWith(agent, new FakeHostedSessionIsolationKeyProvider(), store);
        await DrainEventsAsync(handler.CreateAsync(
            NewConversationTurn(ConversationId, "first question"),
            NewServingContext("resp_" + new string('7', 46), []),
            CancellationToken.None));

        // Act: a second turn of the same conversation, for which the service now reports history.
        captured.Clear();
        await DrainEventsAsync(handler.CreateAsync(
            NewConversationTurn(ConversationId, "second question"),
            NewServingContext("resp_" + new string('8', 46), [NewHistoryMessageItem("msg_hist_1", "first question")]),
            CancellationToken.None));

        // Assert: a persisted session says a prior turn ran here, not that the conversation is inside it.
        // An agent with nothing of its own to remember it with starts each turn empty, so withholding
        // the history would leave it answering blind.
        Assert.Contains(captured, m => m.Text.Contains("first question", StringComparison.Ordinal));
    }

    [Fact]
    public async Task CreateAsync_WhenTheModelReportsAConversationId_TurnsStillCompleteAsync()
    {
        // Arrange: a container whose model call reports a conversation id, which is what happens when
        // the container's chat client lets the model keep the conversation. The agent records that id on
        // the session, and from then on its own conflict policy would reject the provider the host
        // registers, failing the turn.
        var agent = new ChatClientAgent(
            CreateCapturingChatClient([], conversationId: "conv-from-the-model"),
            new ChatClientAgentOptions { Name = "hosted" });
        var handler = BuildHandlerWith(agent, new FakeHostedSessionIsolationKeyProvider(), new InMemoryAgentSessionStore());

        // Act
        var first = await CollectEventNamesAsync(handler, "conv-model", "resp_" + new string('9', 46), "first question");
        var second = await CollectEventNamesAsync(handler, "conv-model", "resp_" + new string('a', 46), "second question");

        // Assert: both turns run to completion. The host owns history for this agent, so the agent's
        // policy of refusing a second history manager must not be left to fire on the host's own
        // registration.
        Assert.Contains("ResponseCompletedEvent", first);
        Assert.DoesNotContain("ResponseFailedEvent", first);
        Assert.Contains("ResponseCompletedEvent", second);
        Assert.DoesNotContain("ResponseFailedEvent", second);
    }

    private static async Task<List<string>> CollectEventNamesAsync(
        AgentFrameworkResponseHandler handler, string conversationId, string responseId, string text)
    {
        var names = new List<string>();
        await foreach (var evt in handler.CreateAsync(
            NewConversationTurn(conversationId, text), NewServingContext(responseId, []), CancellationToken.None))
        {
            names.Add(evt.GetType().Name);
        }

        return names;
    }

    private static CreateResponse NewConversationTurn(string conversationId, string text)
    {
        var request = new CreateResponse { Model = "test" };
        request.Conversation = BinaryData.FromString($"\"{conversationId}\"");
        request.Input = BinaryData.FromObjectAsJson(new[]
        {
            new { type = "message", id = "msg_" + Guid.NewGuid().ToString("N")[..8], status = "completed", role = "user",
                  content = new[] { new { type = "input_text", text } } }
        });
        return request;
    }

    private static ResponseContext NewServingContext(string responseId, IReadOnlyList<OutputItem> history)
    {
        var ctx = new Mock<ResponseContext>(responseId) { CallBase = true };
        ctx.Setup(x => x.PlatformContext).Returns(new PlatformContext("alice", null));
        ctx.Setup(x => x.GetHistoryAsync(It.IsAny<CancellationToken>())).ReturnsAsync(history);
        ctx.Setup(x => x.GetInputItemsAsync(It.IsAny<bool>(), It.IsAny<CancellationToken>())).ReturnsAsync(Array.Empty<Item>());
        return ctx.Object;
    }

    #endregion

    #region Chat history source routing

    // These tests pin down who supplies the conversation history to a hosted agent. Three of them are
    // regression tests for the behaviour this region replaced: the handler used to fetch the platform
    // history and prepend it to the input of every turn, while a ChatClientAgent independently ran its
    // own ChatHistoryProvider. Against that older handler these three fail:
    //   - DoesNotCopyPlatformHistoryIntoTheSession           (the service's turns ended up in the session)
    //   - DoesNotAskItToStorePlatformHistory                 (and in a custom provider's own database)
    //   - TakesThePlatformHistoryInsteadOfThatProvider       (both sources reached the model at once)

    [Fact]
    public async Task CreateAsync_AgentThatIsNotAChatClientAgent_ReceivesOnlyTheNewInputAsync()
    {
        // Arrange: a plain AIAgent, a hosted workflow for instance, carries the conversation in its own
        // session state and picks up where it left off.
        var agent = new CapturingAgent();
        var handler = BuildHandlerWith(agent, new FakeHostedSessionIsolationKeyProvider(), new InMemoryAgentSessionStore());
        var (request, ctx) = BuildChainRequest("resp_" + new string('1', 46), callId: null);
        ctx.Setup(x => x.GetHistoryAsync(It.IsAny<CancellationToken>()))
           .ReturnsAsync([NewHistoryMessageItem("msg_hist_1", "earlier turn")]);

        // Act
        await DrainEventsAsync(handler.CreateAsync(request, ctx.Object, CancellationToken.None));

        // Assert: only this turn's input goes in. Replaying the earlier turns would re-drive steps such
        // an agent has already run.
        Assert.NotNull(agent.CapturedMessages);
        Assert.DoesNotContain(agent.CapturedMessages!, m => m.Text.Contains("earlier turn", StringComparison.Ordinal));
        Assert.Contains(agent.CapturedMessages!, m => m.Text.Contains("Hello", StringComparison.Ordinal));
    }

    [Fact]
    public async Task CreateAsync_ChatClientAgentWithoutHistoryProvider_SendsPlatformHistoryExactlyOnceAsync()
    {
        // Arrange: no chat history provider was supplied, so the platform stays the source and the
        // handler registers FoundryChatHistoryProvider for the turn.
        var captured = new List<ChatMessage>();
        var agent = new ChatClientAgent(CreateCapturingChatClient(captured));
        var handler = BuildHandlerWith(agent, new FakeHostedSessionIsolationKeyProvider(), new InMemoryAgentSessionStore());
        var (request, ctx) = BuildChainRequest("resp_" + new string('2', 46), callId: null);
        ctx.Setup(x => x.GetHistoryAsync(It.IsAny<CancellationToken>()))
           .ReturnsAsync([NewHistoryMessageItem("msg_hist_1", "earlier turn")]);

        // Act
        await DrainEventsAsync(handler.CreateAsync(request, ctx.Object, CancellationToken.None));

        // Assert: the earlier turn still reaches the model, and only one copy of it does.
        Assert.Single(captured, m => m.Text.Contains("earlier turn", StringComparison.Ordinal));
    }

    [Fact]
    public async Task CreateAsync_ChatClientAgentWithHistoryProvider_DoesNotAskItToStorePlatformHistoryAsync()
    {
        // Arrange: an agent whose own provider records everything it is asked to store, and a platform
        // that already holds an earlier turn of this conversation.
        var recordingProvider = new RecordingChatHistoryProvider();
        var agent = new ChatClientAgent(
            CreateCapturingChatClient([]),
            new ChatClientAgentOptions { ChatHistoryProvider = recordingProvider });
        var handler = BuildHandlerWith(agent, new FakeHostedSessionIsolationKeyProvider(), new InMemoryAgentSessionStore());
        var (request, ctx) = BuildChainRequest("resp_" + new string('5', 46), callId: null);
        ctx.Setup(x => x.GetHistoryAsync(It.IsAny<CancellationToken>()))
           .ReturnsAsync([NewHistoryMessageItem("msg_hist_1", "already kept by the service")]);

        // Act
        await DrainEventsAsync(handler.CreateAsync(request, ctx.Object, CancellationToken.None));

        // Assert: the agent's own store must not be told to write a turn the service already holds. The
        // older handler passed that turn in as ordinary input, and since platform items carry no
        // chat-history source marker the provider took it for newly written content and stored it,
        // duplicating into the agent's own database a conversation the service was already keeping.
        Assert.DoesNotContain(recordingProvider.Stored, m => m.Text.Contains("already kept by the service", StringComparison.Ordinal));
    }

    [Fact]
    public async Task CreateAsync_ChatClientAgentWithoutHistoryProvider_DoesNotCopyPlatformHistoryIntoTheSessionAsync()
    {
        // Arrange: the model inside the container keeps the conversation, so it reports a conversation
        // id of its own, and the platform reports one earlier turn for the same conversation.
        const string ResponseId = "resp_" + "4444444444444444444444444444444444444444444444";
        var store = new InMemoryAgentSessionStore();
        var agent = new ChatClientAgent(CreateCapturingChatClient([], conversationId: "conv-model"));
        var handler = BuildHandlerWith(agent, new FakeHostedSessionIsolationKeyProvider(), store);
        var (request, ctx) = BuildChainRequest(ResponseId, callId: null);
        ctx.Setup(x => x.GetHistoryAsync(It.IsAny<CancellationToken>()))
           .ReturnsAsync([NewHistoryMessageItem("msg_hist_1", "already kept by the service")]);

        // Act
        await DrainEventsAsync(handler.CreateAsync(request, ctx.Object, CancellationToken.None));

        // Assert: the model and the service are both keeping this conversation, so the container keeps
        // none of it. The older handler fed the service's history to the agent as ordinary input, and
        // because platform items carry no chat-history source marker the agent's default in-memory
        // provider stored it as if this turn had produced it, leaving a third copy on disk that then
        // drifts from the other two.
        Assert.DoesNotContain("already kept by the service", await SerializedSessionOfAsync(agent, store, ResponseId), StringComparison.Ordinal);
    }

    [Fact]
    public async Task CreateAsync_ChatClientAgentWithHistoryProvider_LeavesThatProviderToSupplyTheHistoryAsync()
    {
        // Arrange: the agent was created with its own chat history provider.
        var captured = new List<ChatMessage>();
        var agent = new ChatClientAgent(
            CreateCapturingChatClient(captured),
            new ChatClientAgentOptions { ChatHistoryProvider = new FixedChatHistoryProvider("from my own store") });
        var handler = BuildHandlerWith(agent, new FakeHostedSessionIsolationKeyProvider(), new InMemoryAgentSessionStore());
        var (request, ctx) = BuildChainRequest("resp_" + new string('3', 46), callId: null);
        ctx.Setup(x => x.GetHistoryAsync(It.IsAny<CancellationToken>()))
           .ReturnsAsync([NewHistoryMessageItem("msg_hist_1", "from the platform")]);

        // Act
        await DrainEventsAsync(handler.CreateAsync(request, ctx.Object, CancellationToken.None));

        // Assert: an agent given a provider keeps it, and hosting adds nothing of its own. Handing it
        // the hosting service's copy as well would put the same conversation in front of the model
        // twice and leave the provider's own store holding turns it never took.
        Assert.Contains(captured, m => m.Text.Contains("from my own store", StringComparison.Ordinal));
        Assert.DoesNotContain(captured, m => m.Text.Contains("from the platform", StringComparison.Ordinal));
    }

    [Fact]
    public async Task CreateAsync_SessionIsGone_RecoversTheHistoryFromTheServiceAsync()
    {
        // Arrange: a turn lands on a container that has no session for the conversation, which is what a
        // restart or a second replica looks like.
        var captured = new List<ChatMessage>();
        var agent = new ChatClientAgent(CreateCapturingChatClient(captured));
        var handler = BuildHandlerWith(agent, new FakeHostedSessionIsolationKeyProvider(), new InMemoryAgentSessionStore());

        // Act
        await DrainEventsAsync(handler.CreateAsync(
            NewConversationRequest("conv-cold", "second question", store: true),
            NewContextServing("resp_" + new string('9', 46), [NewHistoryMessageItem("msg_hist_1", "first question")]),
            CancellationToken.None));

        // Assert: nothing inside the container remembers this conversation, and nothing needs to. The
        // AgentServer SDK's storage provider holds it and hands it back, so the turn runs as if the
        // container had served every one before it.
        Assert.Single(captured, m => m.Text.Contains("first question", StringComparison.Ordinal));
    }

    [Fact]
    public async Task CreateAsync_UnstoredRequestAndAgentWithARawRepresentationFactory_KeepsBothAsync()
    {
        // Arrange: an agent whose own ChatOptions carry a raw representation factory, the way a container
        // adds settings the chat client only understands in its own request type. The caller asks for a
        // turn the service must not store.
        ChatOptions? sentToTheClient = null;
        var client = new Mock<IChatClient>();
        client.Setup(c => c.GetStreamingResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(), It.IsAny<ChatOptions>(), It.IsAny<CancellationToken>()))
            .Returns((IEnumerable<ChatMessage> _, ChatOptions? options, CancellationToken _) =>
            {
                sentToTheClient = options;
                return ToAsyncEnumerableUpdatesAsync(new ChatResponseUpdate(ChatRole.Assistant, "ok") { MessageId = "resp_msg_1" });
            });

        var agent = new ChatClientAgent(client.Object, new ChatClientAgentOptions
        {
            ChatOptions = new ChatOptions
            {
                RawRepresentationFactory = _ => new CreateResponseOptions { EndUserId = "set by the container" },
            },
        });
        var handler = BuildHandlerWith(agent, new FakeHostedSessionIsolationKeyProvider(), new InMemoryAgentSessionStore());

        // Act
        await DrainEventsAsync(handler.CreateAsync(
            NewConversationRequest("conv-raw", "a question", store: false),
            NewContextServing("resp_" + new string('7', 46), []),
            CancellationToken.None));

        // Assert: the agent chains a request factory with its own by taking the agent's only when the
        // request's returns null, so a request factory that always answers would silently drop whatever
        // the container configured. Both settings have to survive on the way to the client.
        Assert.NotNull(sentToTheClient?.RawRepresentationFactory);
        var raw = Assert.IsType<CreateResponseOptions>(sentToTheClient!.RawRepresentationFactory!(client.Object));
        Assert.False(raw.StoredOutputEnabled);
        Assert.Equal("set by the container", raw.EndUserId);
    }

    [Fact]
    public async Task CreateAsync_AgentWhoseChatClientStoredTheTurn_FailsTheRequestAsync()
    {
        // Arrange: a chat client whose underlying service keeps the conversation and says so on every
        // answer, whatever the host asks of it.
        var client = new Mock<IChatClient>();
        client.Setup(c => c.GetStreamingResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(), It.IsAny<ChatOptions>(), It.IsAny<CancellationToken>()))
            .Returns(() => ToAsyncEnumerableUpdatesAsync(
                new ChatResponseUpdate(ChatRole.Assistant, "ok") { MessageId = "resp_msg_1", ConversationId = "conv-downstream" }));

        var agent = new ChatClientAgent(client.Object);
        var handler = BuildHandlerWith(agent, new FakeHostedSessionIsolationKeyProvider(), new InMemoryAgentSessionStore());

        // Act + Assert: the hosting service already recorded this turn, so a second recording held by
        // the service behind the chat client has no owner and no way to stay in step. The container was
        // deployed wrong, which is nothing the caller can fix, so the very first turn fails as a server
        // error rather than quietly building a conversation nobody can reconcile.
        var failure = await Assert.ThrowsAsync<ResponsesApiException>(() => DrainEventsAsync(handler.CreateAsync(
            NewConversationRequest("conv-rejected", "first question", store: true),
            NewContextServing("resp_" + new string('3', 45) + "0", []),
            CancellationToken.None)));

        Assert.Equal("agent_stored_output_not_disabled", failure.Error.Code);
        Assert.Equal(501, failure.StatusCode);
    }

    [Fact]
    public async Task CreateAsync_AgentWhoseChatClientStoredTheTurn_NeverReportsTheTurnCompletedAsync()
    {
        // Arrange: a chat client whose service keeps the conversation, on an agent that does not object
        // to being handed a second history manager. Its run therefore succeeds and the session comes
        // back carrying the id, which is the case where the turn looks fine right up to the end.
        var client = new Mock<IChatClient>();
        client.Setup(c => c.GetStreamingResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(), It.IsAny<ChatOptions>(), It.IsAny<CancellationToken>()))
            .Returns(() => ToAsyncEnumerableUpdatesAsync(
                new ChatResponseUpdate(ChatRole.Assistant, "ok") { MessageId = "resp_msg_1", ConversationId = "conv-downstream" }));

        var agent = new ChatClientAgent(client.Object, new ChatClientAgentOptions
        {
            ThrowOnChatHistoryProviderConflict = false,
            WarnOnChatHistoryProviderConflict = false,
        });

        var handler = BuildHandlerWith(agent, new FakeHostedSessionIsolationKeyProvider(), new InMemoryAgentSessionStore());

        // Act: collect whatever reaches the caller before the failure.
        var seen = new List<string>();
        await Assert.ThrowsAsync<ResponsesApiException>(async () =>
        {
            await foreach (var evt in handler.CreateAsync(
                NewConversationRequest("conv-no-completed", "first question", store: true),
                NewContextServing("resp_" + new string('7', 45) + "0", []),
                CancellationToken.None))
            {
                seen.Add(evt.GetType().Name);
            }
        });

        // Assert: a turn this container will not stand behind is never announced as completed first.
        // Telling the caller it finished and then dropping the connection leaves two different answers
        // for the same turn.
        Assert.DoesNotContain("ResponseCompletedEvent", seen);
    }

    [Fact]
    public async Task CreateAsync_AgentWhoseChatClientStoredTheTurn_AndStoringIsAllowed_SucceedsAsync()
    {
        // Arrange: the same agent, in a container that opted into keeping its own recording.
        var client = new Mock<IChatClient>();
        client.Setup(c => c.GetStreamingResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(), It.IsAny<ChatOptions>(), It.IsAny<CancellationToken>()))
            .Returns(() => ToAsyncEnumerableUpdatesAsync(
                new ChatResponseUpdate(ChatRole.Assistant, "ok") { MessageId = "resp_msg_1", ConversationId = "conv-downstream" }));

        var agent = new ChatClientAgent(client.Object);
        var handler = BuildHandlerWith(
            agent,
            new FakeHostedSessionIsolationKeyProvider(),
            new InMemoryAgentSessionStore(),
            hostingOptions: new FoundryResponsesOptions { AllowStoredOutputEnabled = true });

        // Act
        var names = new List<string>();
        await foreach (var evt in handler.CreateAsync(
            NewConversationRequest("conv-allowed", "first question", store: true),
            NewContextServing("resp_" + new string('4', 45) + "0", []),
            CancellationToken.None))
        {
            names.Add(evt.GetType().Name);
        }

        // Assert: nothing is checked and nothing is refused. The agent is left to run against its own
        // service exactly as the container built it.
        Assert.DoesNotContain("ResponseFailedEvent", names);
    }

    [Fact]
    public async Task CreateAsync_StoringIsAllowed_ResumedTurnDoesNotAlsoGetThePlatformHistoryAsync()
    {
        // Arrange: a container that allows its own service to keep the conversation. Once that service
        // holds it, it adds the earlier turns to the run itself.
        var captured = new List<ChatMessage>();
        var agent = new ChatClientAgent(
            CreateCapturingChatClient(captured, conversationId: "conv-downstream"),
            new ChatClientAgentOptions { Name = "keeps-its-own" });

        var store = new InMemoryAgentSessionStore();
        var handler = BuildHandlerWith(
            agent,
            new FakeHostedSessionIsolationKeyProvider(),
            store,
            hostingOptions: new FoundryResponsesOptions { AllowStoredOutputEnabled = true });

        // First turn: nothing holds the conversation yet, so the platform history is what seeds it.
        await DrainEventsAsync(handler.CreateAsync(
            NewConversationRequest("conv-owned", "first question", store: true),
            NewContextServing("resp_" + new string('b', 45) + "0", []),
            CancellationToken.None));

        // Act: a second turn, for which the platform now reports the first one as history.
        captured.Clear();
        await DrainEventsAsync(handler.CreateAsync(
            NewConversationRequest("conv-owned", "second question", store: true),
            NewContextServing("resp_" + new string('b', 45) + "1", [NewHistoryMessageItem("msg_hist_1", "first question")]),
            CancellationToken.None));

        // Assert: only this turn's input goes in. The service holding the conversation replays the
        // earlier turns on its own, so sending the platform's copy as well would hand the model every
        // earlier turn twice.
        Assert.DoesNotContain(captured, m => m.Text.Contains("first question", StringComparison.Ordinal));
        Assert.Contains(captured, m => m.Text.Contains("second question", StringComparison.Ordinal));
    }

    [Fact]
    public async Task CreateAsync_ChatClientAgent_TakesTheWholeConversationFromTheHostingServiceAsync()
    {
        // Arrange: the AgentServer SDK's storage provider holds the conversation, which is the only
        // place it lives.
        var captured = new List<ChatMessage>();
        var agent = new ChatClientAgent(CreateCapturingChatClient(captured));
        var handler = BuildHandlerWith(agent, new FakeHostedSessionIsolationKeyProvider(), new InMemoryAgentSessionStore());

        await DrainEventsAsync(handler.CreateAsync(
            NewConversationRequest("conv-single-source", "first question", store: true),
            NewContextServing("resp_" + new string('4', 45) + "0", []),
            CancellationToken.None));
        captured.Clear();

        // Act: a second turn, with that storage provider serving the first one back.
        await DrainEventsAsync(handler.CreateAsync(
            NewConversationRequest("conv-single-source", "second question", store: true),
            NewContextServing("resp_" + new string('4', 45) + "1", [NewHistoryMessageItem("msg_hist_1", "first question")]),
            CancellationToken.None));

        // Assert: what it holds plus this turn's input, each exactly once.
        Assert.Single(captured, m => m.Text.Contains("first question", StringComparison.Ordinal));
        Assert.Single(captured, m => m.Text.Contains("second question", StringComparison.Ordinal));
    }

    [Fact]
    public async Task CreateAsync_StoredRequest_StillAsksTheChatClientNotToStoreAsync()
    {
        // Arrange: the caller asks for the turn to be stored.
        ChatOptions? sentToTheClient = null;
        var client = new Mock<IChatClient>();
        client.Setup(c => c.GetStreamingResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(), It.IsAny<ChatOptions>(), It.IsAny<CancellationToken>()))
            .Returns((IEnumerable<ChatMessage> _, ChatOptions? options, CancellationToken _) =>
            {
                sentToTheClient = options;
                return ToAsyncEnumerableUpdatesAsync(new ChatResponseUpdate(ChatRole.Assistant, "ok") { MessageId = "resp_msg_1" });
            });

        var agent = new ChatClientAgent(client.Object);
        var handler = BuildHandlerWith(agent, new FakeHostedSessionIsolationKeyProvider(), new InMemoryAgentSessionStore());

        // Act
        await DrainEventsAsync(handler.CreateAsync(
            NewConversationRequest("conv-never-downstream", "a question", store: true),
            NewContextServing("resp_" + new string('5', 45) + "0", []),
            CancellationToken.None));

        // Assert: storing is the AgentServer SDK's job, done by its storage provider around this
        // handler. Letting the service behind the chat client store as well writes the same
        // conversation twice, in two places that then drift apart.
        Assert.NotNull(sentToTheClient?.RawRepresentationFactory);
        var raw = Assert.IsType<CreateResponseOptions>(sentToTheClient!.RawRepresentationFactory!(client.Object));
        Assert.False(raw.StoredOutputEnabled);

        // And because nothing is stored, reasoning would be lost between turns unless its encrypted
        // form is asked for, which is what AsIChatClientWithStoredOutputDisabled does too.
        Assert.Contains(IncludedResponseProperty.ReasoningEncryptedContent, raw.IncludedProperties);
    }

    [Fact]
    public async Task CreateAsync_ReasoningEncryptedContentTurnedOff_IsNotAskedForAsync()
    {
        // Arrange: a container that does not want the encrypted reasoning tokens asked for.
        ChatOptions? sentToTheClient = null;
        var client = new Mock<IChatClient>();
        client.Setup(c => c.GetStreamingResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(), It.IsAny<ChatOptions>(), It.IsAny<CancellationToken>()))
            .Returns((IEnumerable<ChatMessage> _, ChatOptions? options, CancellationToken _) =>
            {
                sentToTheClient = options;
                return ToAsyncEnumerableUpdatesAsync(new ChatResponseUpdate(ChatRole.Assistant, "ok") { MessageId = "resp_msg_1" });
            });

        var agent = new ChatClientAgent(client.Object);
        var handler = BuildHandlerWith(
            agent,
            new FakeHostedSessionIsolationKeyProvider(),
            new InMemoryAgentSessionStore(),
            hostingOptions: new FoundryResponsesOptions { IncludeReasoningEncryptedContent = false });

        // Act
        await DrainEventsAsync(handler.CreateAsync(
            NewConversationRequest("conv-no-reasoning", "a question", store: true),
            NewContextServing("resp_" + new string('6', 45) + "0", []),
            CancellationToken.None));

        // Assert: storing is still turned off, but nothing else is added to the request.
        var raw = Assert.IsType<CreateResponseOptions>(sentToTheClient!.RawRepresentationFactory!(client.Object));
        Assert.False(raw.StoredOutputEnabled);
        Assert.DoesNotContain(IncludedResponseProperty.ReasoningEncryptedContent, raw.IncludedProperties);
    }

    [Fact]
    public async Task CreateAsync_StoringIsAllowed_LeavesTheAgentsOwnSettingAloneAsync()
    {
        // Arrange: a container that opted into keeping its own recording, with an agent that asks for
        // its responses to be stored.
        ChatOptions? sentToTheClient = null;
        var client = new Mock<IChatClient>();
        client.Setup(c => c.GetStreamingResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(), It.IsAny<ChatOptions>(), It.IsAny<CancellationToken>()))
            .Returns((IEnumerable<ChatMessage> _, ChatOptions? options, CancellationToken _) =>
            {
                sentToTheClient = options;
                return ToAsyncEnumerableUpdatesAsync(new ChatResponseUpdate(ChatRole.Assistant, "ok") { MessageId = "resp_msg_1" });
            });

        var agent = new ChatClientAgent(client.Object, new ChatClientAgentOptions
        {
            ChatOptions = new ChatOptions
            {
                RawRepresentationFactory = _ => new CreateResponseOptions { StoredOutputEnabled = true },
            },
        });

        var handler = BuildHandlerWith(
            agent,
            new FakeHostedSessionIsolationKeyProvider(),
            new InMemoryAgentSessionStore(),
            hostingOptions: new FoundryResponsesOptions { AllowStoredOutputEnabled = true });

        // Act
        await DrainEventsAsync(handler.CreateAsync(
            NewConversationRequest("conv-allowed-setting", "a question", store: true),
            NewContextServing("resp_" + new string('8', 45) + "0", []),
            CancellationToken.None));

        // Assert: what the container configured is what goes out, untouched.
        var raw = Assert.IsType<CreateResponseOptions>(sentToTheClient!.RawRepresentationFactory!(client.Object));
        Assert.True(raw.StoredOutputEnabled);
    }

    [Fact]
    public async Task CreateAsync_AgentSpeakingChatCompletions_AlsoAsksItNotToStoreAsync()
    {
        // Arrange: a container whose chat client speaks Chat Completions rather than Responses, so the
        // request it understands is a ChatCompletionOptions.
        ChatOptions? sentToTheClient = null;
        var client = new Mock<IChatClient>();
        client.Setup(c => c.GetStreamingResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(), It.IsAny<ChatOptions>(), It.IsAny<CancellationToken>()))
            .Returns((IEnumerable<ChatMessage> _, ChatOptions? options, CancellationToken _) =>
            {
                sentToTheClient = options;
                return ToAsyncEnumerableUpdatesAsync(new ChatResponseUpdate(ChatRole.Assistant, "ok") { MessageId = "resp_msg_1" });
            });

        var agent = new ChatClientAgent(client.Object, new ChatClientAgentOptions
        {
            ChatOptions = new ChatOptions
            {
                RawRepresentationFactory = _ => new ChatCompletionOptions { EndUserId = "set by the container" },
            },
        });
        var handler = BuildHandlerWith(agent, new FakeHostedSessionIsolationKeyProvider(), new InMemoryAgentSessionStore());

        // Act
        await DrainEventsAsync(handler.CreateAsync(
            NewConversationRequest("conv-completions", "a question", store: true),
            NewContextServing("resp_" + new string('6', 45) + "0", []),
            CancellationToken.None));

        // Assert: the setting has the same name on both OpenAI request shapes, so a chat client speaking
        // either protocol is covered, and what the container configured survives alongside it.
        Assert.NotNull(sentToTheClient?.RawRepresentationFactory);
        var raw = Assert.IsType<ChatCompletionOptions>(sentToTheClient!.RawRepresentationFactory!(client.Object));
        Assert.False(raw.StoredOutputEnabled);
        Assert.Equal("set by the container", raw.EndUserId);
    }

    private static CreateResponse NewConversationRequest(string conversationId, string text, bool store)
    {
        var request = new CreateResponse { Model = "test", Store = store };
        request.Conversation = BinaryData.FromString($"\"{conversationId}\"");
        request.Input = BinaryData.FromObjectAsJson(new[]
        {
            new { type = "message", id = "msg_" + Guid.NewGuid().ToString("N")[..8], status = "completed", role = "user",
                  content = new[] { new { type = "input_text", text } } }
        });
        return request;
    }

    private static ResponseContext NewContextServing(string responseId, IReadOnlyList<OutputItem> history)
    {
        var ctx = new Mock<ResponseContext>(responseId) { CallBase = true };
        ctx.Setup(x => x.PlatformContext).Returns(new PlatformContext("alice", null));
        ctx.Setup(x => x.GetHistoryAsync(It.IsAny<CancellationToken>())).ReturnsAsync(history);
        ctx.Setup(x => x.GetInputItemsAsync(It.IsAny<bool>(), It.IsAny<CancellationToken>())).ReturnsAsync(Array.Empty<Item>());
        return ctx.Object;
    }

    /// <summary>Reads back the session the handler persisted for a response and returns it as JSON text.</summary>
    private static async Task<string> SerializedSessionOfAsync(AIAgent agent, InMemoryAgentSessionStore store, string responseId)
    {
        var sessionKey = HostedConversationKey.Resolve(conversationId: null, previousResponseId: null, responseId);
        var session = await store.GetSessionAsync(agent, sessionKey!, FakeHostedSessionIsolationKeyProvider.DefaultUserId, CancellationToken.None);

        // The handler persists the session at the end of every turn, so a missing one means the turn did
        // not get that far and the assertions below would otherwise pass without proving anything.
        Assert.NotNull(session);

        var serialized = await agent.SerializeSessionAsync(session, cancellationToken: CancellationToken.None);
        return serialized.GetRawText();
    }

    private static OutputItemMessage NewHistoryMessageItem(string id, string text) =>
        new(
            id: id,
            role: MessageRole.Assistant,
            content: [new MessageContentOutputTextContent(text, Array.Empty<Annotation>(), Array.Empty<LogProb>())],
            status: MessageStatus.Completed);

    private static IChatClient CreateCapturingChatClient(List<ChatMessage> captured, string? conversationId = null)
    {
        var mock = new Mock<IChatClient>();
        mock.Setup(c => c.GetStreamingResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>()))
            .Returns((IEnumerable<ChatMessage> messages, ChatOptions? options, CancellationToken _) =>
            {
                captured.AddRange(messages);

                // Mirror the MEAI OpenAI adapter, which reports no conversation id for a response the
                // service was not asked to store: OpenAIResponsesChatClient sets ChatResponse.ConversationId
                // to null whenever CreateResponseOptions.StoredOutputEnabled is false. Without that rule
                // here a fake would keep handing back a stored thread the caller opted out of.
                var storedOutputDisabled =
                    options?.RawRepresentationFactory?.Invoke(mock.Object) is CreateResponseOptions { StoredOutputEnabled: false };

                return ToAsyncEnumerableUpdatesAsync(
                    new ChatResponseUpdate(ChatRole.Assistant, "ok")
                    {
                        MessageId = "resp_msg_1",
                        ConversationId = storedOutputDisabled ? null : conversationId,
                    });
            });
        return mock.Object;
    }

    private static async IAsyncEnumerable<ChatResponseUpdate> ToAsyncEnumerableUpdatesAsync(params ChatResponseUpdate[] updates)
    {
        foreach (var update in updates)
        {
            yield return update;
        }

        await Task.CompletedTask;
    }

    /// <summary>A chat history provider that always returns the same message, standing in for one backed by a store.</summary>
    private sealed class FixedChatHistoryProvider(string text) : ChatHistoryProvider
    {
        protected override ValueTask<IEnumerable<ChatMessage>> ProvideChatHistoryAsync(InvokingContext context, CancellationToken cancellationToken = default)
            => new([new ChatMessage(ChatRole.User, text)]);

        protected override ValueTask StoreChatHistoryAsync(InvokedContext context, CancellationToken cancellationToken = default) => default;
    }

    /// <summary>A chat history provider that records everything it is asked to write, standing in for one backed by a database.</summary>
    private sealed class RecordingChatHistoryProvider : ChatHistoryProvider
    {
        public List<ChatMessage> Stored { get; } = [];

        protected override ValueTask<IEnumerable<ChatMessage>> ProvideChatHistoryAsync(InvokingContext context, CancellationToken cancellationToken = default)
            => new([]);

        protected override ValueTask StoreChatHistoryAsync(InvokedContext context, CancellationToken cancellationToken = default)
        {
            this.Stored.AddRange(context.RequestMessages);
            if (context.ResponseMessages is not null)
            {
                this.Stored.AddRange(context.ResponseMessages);
            }

            return default;
        }
    }

    #endregion

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
            new(new SimpleAgentSession());

        protected override ValueTask<JsonElement> SerializeSessionCoreAsync(
            AgentSession session,
            JsonSerializerOptions? jsonSerializerOptions,
            CancellationToken cancellationToken = default) =>
            new(JsonDocument.Parse("{}").RootElement);

        protected override ValueTask<AgentSession> DeserializeSessionCoreAsync(
            JsonElement serializedState,
            JsonSerializerOptions? jsonSerializerOptions,
            CancellationToken cancellationToken = default) =>
            new(new SimpleAgentSession());
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
            new(new SimpleAgentSession());

        protected override ValueTask<JsonElement> SerializeSessionCoreAsync(
            AgentSession session,
            JsonSerializerOptions? jsonSerializerOptions,
            CancellationToken cancellationToken = default) =>
            new(JsonDocument.Parse("{}").RootElement);

        protected override ValueTask<AgentSession> DeserializeSessionCoreAsync(
            JsonElement serializedState,
            JsonSerializerOptions? jsonSerializerOptions,
            CancellationToken cancellationToken = default) =>
            new(new SimpleAgentSession());
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
            new(new SimpleAgentSession());

        protected override ValueTask<JsonElement> SerializeSessionCoreAsync(
            AgentSession session,
            JsonSerializerOptions? jsonSerializerOptions,
            CancellationToken cancellationToken = default) =>
            new(JsonDocument.Parse("{}").RootElement);

        protected override ValueTask<AgentSession> DeserializeSessionCoreAsync(
            JsonElement serializedState,
            JsonSerializerOptions? jsonSerializerOptions,
            CancellationToken cancellationToken = default) =>
            new(new SimpleAgentSession());
    }

    /// <summary>
    /// Stands in for a hosted workflow: an <see cref="AIAgent"/> that is not a <see cref="ChatClientAgent"/>
    /// and keeps the conversation in its own session, so the handler leaves its history alone.
    /// </summary>
    private sealed class WorkflowLikeAgent : AIAgent
    {
        public IEnumerable<ChatMessage>? CapturedMessages { get; private set; }

        protected override IAsyncEnumerable<AgentResponseUpdate> RunCoreStreamingAsync(
            IEnumerable<ChatMessage> messages,
            AgentSession? session,
            AgentRunOptions? options,
            CancellationToken cancellationToken = default)
        {
            this.CapturedMessages = messages.ToList();
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
            new(new SimpleAgentSession());

        protected override ValueTask<JsonElement> SerializeSessionCoreAsync(
            AgentSession session,
            JsonSerializerOptions? jsonSerializerOptions,
            CancellationToken cancellationToken = default) =>
            new(JsonDocument.Parse("{}").RootElement);

        protected override ValueTask<AgentSession> DeserializeSessionCoreAsync(
            JsonElement serializedState,
            JsonSerializerOptions? jsonSerializerOptions,
            CancellationToken cancellationToken = default) =>
            new(new SimpleAgentSession());
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
            new(new SimpleAgentSession());

        protected override ValueTask<JsonElement> SerializeSessionCoreAsync(
            AgentSession session,
            JsonSerializerOptions? jsonSerializerOptions,
            CancellationToken cancellationToken = default) =>
            new(JsonDocument.Parse("{}").RootElement);

        protected override ValueTask<AgentSession> DeserializeSessionCoreAsync(
            JsonElement serializedState,
            JsonSerializerOptions? jsonSerializerOptions,
            CancellationToken cancellationToken = default) =>
            new(new SimpleAgentSession());
    }

    [Fact]
    public async Task CreateAsync_PreviousResponseIdChain_NoConversation_ReusesOneSessionAsync()
    {
        // Arrange
        var agent = new SessionCountingAgent();
        var fakeProvider = new FakeHostedSessionIsolationKeyProvider("alice");
        var store = new InMemoryAgentSessionStore();
        var handler = BuildHandlerWith(agent, fakeProvider, store);

        const string PartitionA = "aaaaaaaaaaaaaaaa00";
        var responseA = "caresp_" + PartitionA + new string('1', 32);
        var responseA2 = "caresp_" + PartitionA + new string('2', 32);

        // Turn 1: cold start, no conversation, no previous_response_id. Key from minted responseA.
        var (req1, ctx1) = BuildChainRequest(responseA, callId: null);
        await DrainEventsAsync(handler.CreateAsync(req1, ctx1.Object, CancellationToken.None));
        Assert.NotNull(agent.LastSession);

        // Turn 2: client echoes previous_response_id sharing the same partition; minted responseA2.
        var (req2, ctx2) = BuildChainRequest(responseA2, callId: null);
        req2.PreviousResponseId = responseA;
        agent.LastSession = null;
        await DrainEventsAsync(handler.CreateAsync(req2, ctx2.Object, CancellationToken.None));

        // Assert: both turns persisted under the same partition key → one created session.
        Assert.NotNull(agent.LastSession);
        Assert.Equal("alice", agent.LastSession!.GetHostedContext()!.UserId);
        Assert.Equal(1, agent.SessionCount);
    }

    [Fact]
    public async Task CreateAsync_SetsCallIdFromPlatformContext_VisibleDuringAgentRunAsync()
    {
        // Arrange
        var agent = new CallIdCapturingAgent();
        var handler = BuildHandlerWith(agent, new FakeHostedSessionIsolationKeyProvider("alice"), new InMemoryAgentSessionStore());
        var (request, ctx) = BuildChainRequest("caresp_" + new string('0', 50), callId: "call-xyz");

        // Act
        await DrainEventsAsync(handler.CreateAsync(request, ctx.Object, CancellationToken.None));

        // Assert: the call id observed inside the agent run (the same async flow that drives any
        // downstream MCP/tool egress) matches the platform-provided value. This guards against the
        // async-iterator AsyncLocal revert that would otherwise drop the call id before egress.
        Assert.Equal("call-xyz", agent.ObservedCallId);
    }

    [Fact]
    public async Task CreateAsync_NoCallIdInPlatformContext_LeavesAmbientNullAsync()
    {
        // Arrange
        var agent = new CallIdCapturingAgent();
        var handler = BuildHandlerWith(agent, new FakeHostedSessionIsolationKeyProvider("alice"), new InMemoryAgentSessionStore());
        var (request, ctx) = BuildChainRequest("caresp_" + new string('0', 50), callId: null);

        // Act
        await DrainEventsAsync(handler.CreateAsync(request, ctx.Object, CancellationToken.None));

        // Assert
        Assert.Null(agent.ObservedCallId);
    }

    [Fact]
    public async Task CreateAsync_AfterStreamCompletes_DoesNotLeakCallIdToCallerContextAsync()
    {
        // Arrange
        var agent = new CallIdCapturingAgent();
        var handler = BuildHandlerWith(agent, new FakeHostedSessionIsolationKeyProvider("alice"), new InMemoryAgentSessionStore());
        var (request, ctx) = BuildChainRequest("caresp_" + new string('0', 50), callId: "call-xyz");

        // The caller's ambient call id starts clear.
        Assert.Null(HostedCallContext.CallId);

        // Act
        await DrainEventsAsync(handler.CreateAsync(request, ctx.Object, CancellationToken.None));

        // Assert: HostedCallContext is documented request-scoped. The handler sets the AsyncLocal inside
        // its streaming iterator (observed by the agent run — see VisibleDuringAgentRun above), but that
        // write never escapes to the caller's execution context. After the stream completes the caller's
        // ambient call id is still null, so a stale call id cannot leak into a subsequent request that is
        // handled on the same thread.
        Assert.Equal("call-xyz", agent.ObservedCallId);
        Assert.Null(HostedCallContext.CallId);
    }

    // ── Multi-agent / multi-user file-system isolation (handler-driven, no live service) ─────────────
    // These drive the hosted-agent handler (the in-process "hosted instance") against a REAL
    // FileSystemAgentSessionStore and the REAL PlatformHostedSessionIsolationKeyProvider (no fake), so the
    // user id is genuinely captured from the request's x-agent-user-id (ResponseContext.PlatformContext).
    // They assert the on-disk layout {root}/a-{agent}/u-{userId}/c-{conv}.json for combinations of agent
    // name and user.

    [Fact]
    public async Task CreateAsync_MultipleUsersSameAgent_WritePerUserDirectoriesAsync()
    {
        var root = NewIsolationTempRoot();
        try
        {
            // Arrange: one store shared by the container, one agent ("concierge"), two users.
            var store = new FileSystemAgentSessionStore(root);
            var handler = BuildMultiAgentHandler(store, ("concierge", new RecordingAgent("concierge")));

            // Act: Alice and Bob each drive the same agent and the same conversation id.
            var (aliceReq, aliceCtx) = BuildUserRequest("concierge", "trip", userId: "alice");
            await DrainEventsAsync(handler.CreateAsync(aliceReq, aliceCtx.Object, CancellationToken.None));
            var (bobReq, bobCtx) = BuildUserRequest("concierge", "trip", userId: "bob");
            await DrainEventsAsync(handler.CreateAsync(bobReq, bobCtx.Object, CancellationToken.None));

            // Assert: each user's session is persisted under its own u-{userId} directory beneath the
            // shared a-{agent} directory; neither can reach the other's path.
            Assert.True(File.Exists(Path.Combine(store.RootDirectory, "a-concierge", "u-alice", "c-trip.json")));
            Assert.True(File.Exists(Path.Combine(store.RootDirectory, "a-concierge", "u-bob", "c-trip.json")));
        }
        finally
        {
            CleanupTempRoot(root);
        }
    }

    [Fact]
    public async Task CreateAsync_MultipleAgentsSameUser_WritePerAgentDirectoriesAsync()
    {
        var root = NewIsolationTempRoot();
        try
        {
            // Arrange: one store shared by the container, two agents, one user.
            var store = new FileSystemAgentSessionStore(root);
            var handler = BuildMultiAgentHandler(store, ("concierge", new RecordingAgent("concierge")), ("scheduler", new RecordingAgent("scheduler")));

            // Act: the same user drives two different agents on the same conversation id.
            var (req1, ctx1) = BuildUserRequest("concierge", "trip", userId: "alice");
            await DrainEventsAsync(handler.CreateAsync(req1, ctx1.Object, CancellationToken.None));
            var (req2, ctx2) = BuildUserRequest("scheduler", "trip", userId: "alice");
            await DrainEventsAsync(handler.CreateAsync(req2, ctx2.Object, CancellationToken.None));

            // Assert: each agent buckets the user's session under its own a-{agent} directory, so two
            // agents in the same container cannot collide on a shared conversation id.
            Assert.True(File.Exists(Path.Combine(store.RootDirectory, "a-concierge", "u-alice", "c-trip.json")));
            Assert.True(File.Exists(Path.Combine(store.RootDirectory, "a-scheduler", "u-alice", "c-trip.json")));
        }
        finally
        {
            CleanupTempRoot(root);
        }
    }

    [Fact]
    public async Task CreateAsync_SecondUserSameConversation_GetsFreshSessionNoLeakAsync()
    {
        var root = NewIsolationTempRoot();
        try
        {
            // Arrange.
            var store = new FileSystemAgentSessionStore(root);
            var agent = new RecordingAgent("concierge");
            var handler = BuildMultiAgentHandler(store, ("concierge", agent));

            // Act: Alice drives twice (cold start then resume), then Bob forges the same agent+conversation.
            var (a1Req, a1Ctx) = BuildUserRequest("concierge", "trip", userId: "alice");
            await DrainEventsAsync(handler.CreateAsync(a1Req, a1Ctx.Object, CancellationToken.None));
            var (a2Req, a2Ctx) = BuildUserRequest("concierge", "trip", userId: "alice");
            await DrainEventsAsync(handler.CreateAsync(a2Req, a2Ctx.Object, CancellationToken.None));
            var (bobReq, bobCtx) = BuildUserRequest("concierge", "trip", userId: "bob");
            await DrainEventsAsync(handler.CreateAsync(bobReq, bobCtx.Object, CancellationToken.None));

            // Assert: Alice's second turn restored her persisted session (a deserialize), while Bob's request
            // produced a freshly created session — Bob never deserialized Alice's state. Two creates total
            // (Alice turn 1, Bob turn 1) and one restore (Alice turn 2).
            Assert.Equal(2, agent.CreateCount);
            Assert.Equal(1, agent.DeserializeCount);
            // And the files live in distinct per-user directories.
            Assert.True(File.Exists(Path.Combine(store.RootDirectory, "a-concierge", "u-alice", "c-trip.json")));
            Assert.True(File.Exists(Path.Combine(store.RootDirectory, "a-concierge", "u-bob", "c-trip.json")));
        }
        finally
        {
            CleanupTempRoot(root);
        }
    }

    [Fact]
    public async Task CreateAsync_NoUserIdCaptured_NotHosted_SucceedsUnscopedAsync()
    {
        var root = NewIsolationTempRoot();
        try
        {
            // Arrange: a non-hosted (local) request whose x-agent-user-id was not captured (PlatformContext
            // is null). Under unit tests FoundryEnvironment.IsHosted is false, so the container is treated as
            // local: per-user isolation is simply not triggered and the request succeeds instead of 500ing.
            // The session is persisted without a u-{userId} segment (unscoped). The hosted-but-missing-user
            // branch (which still rejects) cannot be unit-tested because FoundryEnvironment.IsHosted is a
            // process-cached static; it is exercised by the investigation repro app's "hosted" scenario.
            var store = new FileSystemAgentSessionStore(root);
            var handler = BuildMultiAgentHandler(store, ("concierge", new RecordingAgent("concierge")));
            var (req, ctx) = BuildUserRequest("concierge", "trip", userId: null);

            // Act: the request drains without throwing.
            await DrainEventsAsync(handler.CreateAsync(req, ctx.Object, CancellationToken.None));

            // Assert: the session is written under the agent bucket with NO per-user (u-*) segment.
            Assert.True(File.Exists(Path.Combine(store.RootDirectory, "a-concierge", "c-trip.json")));
            var agentDir = Path.Combine(store.RootDirectory, "a-concierge");
            Assert.Empty(Directory.GetDirectories(agentDir, "u-*"));
        }
        finally
        {
            CleanupTempRoot(root);
        }
    }

    private static string NewIsolationTempRoot()
        => Path.Combine(Path.GetTempPath(), "handler-fs-isolation-" + Guid.NewGuid().ToString("N"));

    private static void CleanupTempRoot(string root)
    {
        try
        {
            if (Directory.Exists(root))
            {
                Directory.Delete(root, recursive: true);
            }
        }
        catch
        {
            // best-effort cleanup
        }
    }

    private static AgentFrameworkResponseHandler BuildMultiAgentHandler(AgentSessionStore store, params (string Name, AIAgent Agent)[] agents)
    {
        var services = new ServiceCollection();
        // Shared default store for the container; agents resolved by name via keyed DI. No isolation-key
        // provider is registered so the real PlatformHostedSessionIsolationKeyProvider reads x-agent-user-id.
        services.AddSingleton(store);
        foreach (var (name, agent) in agents)
        {
            services.AddKeyedSingleton(name, agent);
        }

        return new AgentFrameworkResponseHandler(services.BuildServiceProvider(), NullLogger<AgentFrameworkResponseHandler>.Instance);
    }

    private static (CreateResponse Request, Mock<ResponseContext> Context) BuildUserRequest(string agentName, string conversationId, string? userId)
    {
        // The agent is selected from the request's Model field (GetAgentName falls back to Model); the
        // conversation id pins the c-{contextId} leaf.
        var request = new CreateResponse { Model = agentName };
        request.Conversation = BinaryData.FromString($"\"{conversationId}\"");
        request.Input = BinaryData.FromObjectAsJson(new[]
        {
            new { type = "message", id = "msg_1", status = "completed", role = "user",
                  content = new[] { new { type = "input_text", text = "Hello" } } }
        });

        var ctx = new Mock<ResponseContext>("caresp_" + new string('0', 50)) { CallBase = true };
        // x-agent-user-id captured -> PlatformContext carries the user id; not captured -> null PlatformContext.
        if (userId is null)
        {
            ctx.Setup(x => x.PlatformContext).Returns((PlatformContext)null!);
        }
        else
        {
            ctx.Setup(x => x.PlatformContext).Returns(new PlatformContext(userId, null));
        }
        ctx.Setup(x => x.GetHistoryAsync(It.IsAny<CancellationToken>())).ReturnsAsync(Array.Empty<OutputItem>());
        ctx.Setup(x => x.GetInputItemsAsync(It.IsAny<bool>(), It.IsAny<CancellationToken>())).ReturnsAsync(Array.Empty<Item>());
        return (request, ctx);
    }

    private static AgentFrameworkResponseHandler BuildHandlerWith(
        AIAgent agent,
        HostedSessionIsolationKeyProvider provider,
        AgentSessionStore store,
        FoundryResponsesOptions? hostingOptions = null)
    {
        var services = new ServiceCollection();
        services.AddSingleton(store);
        services.AddSingleton(agent);
        services.AddSingleton(provider);
        if (hostingOptions is not null)
        {
            services.AddSingleton(Options.Create(hostingOptions));
        }

        return new AgentFrameworkResponseHandler(services.BuildServiceProvider(), NullLogger<AgentFrameworkResponseHandler>.Instance);
    }

    private static (CreateResponse Request, Mock<ResponseContext> Context) BuildChainRequest(string responseId, string? callId)
    {
        var request = new CreateResponse { Model = "test" };
        request.Input = BinaryData.FromObjectAsJson(new[]
        {
            new { type = "message", id = "msg_1", status = "completed", role = "user",
                  content = new[] { new { type = "input_text", text = "Hello" } } }
        });
        var ctx = new Mock<ResponseContext>(responseId) { CallBase = true };
        ctx.Setup(x => x.PlatformContext).Returns(new PlatformContext("alice", callId));
        ctx.Setup(x => x.GetHistoryAsync(It.IsAny<CancellationToken>())).ReturnsAsync(Array.Empty<OutputItem>());
        ctx.Setup(x => x.GetInputItemsAsync(It.IsAny<bool>(), It.IsAny<CancellationToken>())).ReturnsAsync(Array.Empty<Item>());
        return (request, ctx);
    }

    private static async Task DrainEventsAsync(IAsyncEnumerable<ResponseStreamEvent> stream)
    {
        await foreach (var _ in stream)
        {
        }
    }

    /// <summary>Stateful agent that counts created sessions and round-trips its <see cref="AgentSessionStateBag"/>.</summary>
    private sealed class SessionCountingAgent : AIAgent
    {
        public AgentSession? LastSession { get; set; }
        public int SessionCount { get; private set; }

        protected override IAsyncEnumerable<AgentResponseUpdate> RunCoreStreamingAsync(
            IEnumerable<ChatMessage> messages, AgentSession? session, AgentRunOptions? options, CancellationToken cancellationToken = default)
        {
            this.LastSession = session;
            return ToAsyncEnumerableAsync(new AgentResponseUpdate { MessageId = "resp_msg_1", Contents = [new MeaiTextContent("ok")] });
        }

        protected override Task<AgentResponse> RunCoreAsync(IEnumerable<ChatMessage> messages, AgentSession? session, AgentRunOptions? options, CancellationToken cancellationToken = default)
            => throw new NotImplementedException();

        protected override ValueTask<AgentSession> CreateSessionCoreAsync(CancellationToken cancellationToken = default)
        {
            this.SessionCount++;
            return new(new StatefulSession());
        }

        protected override ValueTask<JsonElement> SerializeSessionCoreAsync(AgentSession session, JsonSerializerOptions? jsonSerializerOptions, CancellationToken cancellationToken = default)
            => new(((StatefulSession)session).Serialize());

        protected override ValueTask<AgentSession> DeserializeSessionCoreAsync(JsonElement serializedState, JsonSerializerOptions? jsonSerializerOptions, CancellationToken cancellationToken = default)
            => new(StatefulSession.Deserialize(serializedState));
    }

    /// <summary>Records how many sessions it created vs deserialized, to prove cross-user no-leak.</summary>
    private sealed class RecordingAgent : AIAgent
    {
        private readonly string? _name;

        public RecordingAgent(string? name = null)
        {
            this._name = name;
        }

        public override string? Name => this._name;

        public int CreateCount { get; private set; }
        public int DeserializeCount { get; private set; }

        protected override IAsyncEnumerable<AgentResponseUpdate> RunCoreStreamingAsync(
            IEnumerable<ChatMessage> messages, AgentSession? session, AgentRunOptions? options, CancellationToken cancellationToken = default)
            => ToAsyncEnumerableAsync(new AgentResponseUpdate { MessageId = "resp_msg_1", Contents = [new MeaiTextContent("ok")] });

        protected override Task<AgentResponse> RunCoreAsync(IEnumerable<ChatMessage> messages, AgentSession? session, AgentRunOptions? options, CancellationToken cancellationToken = default)
            => throw new NotImplementedException();

        protected override ValueTask<AgentSession> CreateSessionCoreAsync(CancellationToken cancellationToken = default)
        {
            this.CreateCount++;
            return new(new StatefulSession());
        }

        protected override ValueTask<JsonElement> SerializeSessionCoreAsync(AgentSession session, JsonSerializerOptions? jsonSerializerOptions, CancellationToken cancellationToken = default)
            => new(((StatefulSession)session).Serialize());

        protected override ValueTask<AgentSession> DeserializeSessionCoreAsync(JsonElement serializedState, JsonSerializerOptions? jsonSerializerOptions, CancellationToken cancellationToken = default)
        {
            this.DeserializeCount++;
            return new(StatefulSession.Deserialize(serializedState));
        }
    }

    /// <summary>Reads <see cref="HostedCallContext.CallId"/> during its run, standing in for a downstream tool call.</summary>
    private sealed class CallIdCapturingAgent : AIAgent
    {
        public string? ObservedCallId { get; private set; }

        protected override IAsyncEnumerable<AgentResponseUpdate> RunCoreStreamingAsync(
            IEnumerable<ChatMessage> messages, AgentSession? session, AgentRunOptions? options, CancellationToken cancellationToken = default)
        {
            this.ObservedCallId = HostedCallContext.CallId;
            return ToAsyncEnumerableAsync(new AgentResponseUpdate { MessageId = "resp_msg_1", Contents = [new MeaiTextContent("ok")] });
        }

        protected override Task<AgentResponse> RunCoreAsync(IEnumerable<ChatMessage> messages, AgentSession? session, AgentRunOptions? options, CancellationToken cancellationToken = default)
            => throw new NotImplementedException();

        protected override ValueTask<AgentSession> CreateSessionCoreAsync(CancellationToken cancellationToken = default)
            => new(new StatefulSession());

        protected override ValueTask<JsonElement> SerializeSessionCoreAsync(AgentSession session, JsonSerializerOptions? jsonSerializerOptions, CancellationToken cancellationToken = default)
            => new(((StatefulSession)session).Serialize());

        protected override ValueTask<AgentSession> DeserializeSessionCoreAsync(JsonElement serializedState, JsonSerializerOptions? jsonSerializerOptions, CancellationToken cancellationToken = default)
            => new(StatefulSession.Deserialize(serializedState));
    }

    private sealed class StatefulSession : AgentSession
    {
        public StatefulSession() { }
        private StatefulSession(AgentSessionStateBag bag) { this.StateBag = bag; }
        public JsonElement Serialize() => this.StateBag.Serialize();
        public static StatefulSession Deserialize(JsonElement e) => new(AgentSessionStateBag.Deserialize(e));
    }

    private sealed class SimpleAgentSession : AgentSession { }
}
