// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.IO;
using System.Runtime.CompilerServices;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.AI;
using Microsoft.Bot.ObjectModel;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.Declarative.UnitTests;

/// <summary>
/// Unit tests for <see cref="YamlAgentFactoryExtensions"/>.
/// </summary>
public class YamlAgentFactoryExtensionsTests
{
    private const string SimpleAgent =
        """
        kind: GptComponentMetadata
        name: TestAgent
        instructions: You are a helpful assistant.
        """;

    private const string ChatClientAgent =
        """
        kind: GptComponentMetadata
        type: chat_client_agent
        name: TestAgent
        description: Test Agent
        instructions: You are a helpful assistant.
        """;

    private const string InvalidYaml =
        """
        invalid: yaml content
        that: doesn't parse correctly
        """;

    private const string EmptyYaml = "";

    [Fact]
    public async Task CreateFromYamlAsync_ValidYaml_CreatesAgentAsync()
    {
        // Arrange
        var agentFactory = new TestAgentFactory();
        var options = new AgentCreationOptions();

        // Act
        var result = await agentFactory.CreateFromYamlAsync(SimpleAgent, options);

        // Assert
        Assert.NotNull(result);
        Assert.IsType<TestAgent>(result);
    }

    [Fact]
    public async Task CreateFromYamlAsync_ValidYamlWithoutOptions_CreatesAgentAsync()
    {
        // Arrange
        var agentFactory = new TestAgentFactory();

        // Act
        var result = await agentFactory.CreateFromYamlAsync(SimpleAgent);

        // Assert
        Assert.NotNull(result);
        Assert.IsType<TestAgent>(result);
    }

    [Fact]
    public async Task CreateFromYamlAsync_ChatClientAgentYaml_CreatesAgentAsync()
    {
        // Arrange
        var agentFactory = new TestAgentFactory();
        var options = new AgentCreationOptions();

        // Act
        var result = await agentFactory.CreateFromYamlAsync(ChatClientAgent, options);

        // Assert
        Assert.NotNull(result);
        Assert.IsType<TestAgent>(result);
    }

    [Fact]
    public async Task CreateFromYamlAsync_NullAgentFactory_ThrowsArgumentNullExceptionAsync()
    {
        // Arrange
        AgentFactory agentFactory = null!;

        // Act & Assert
        await Assert.ThrowsAsync<ArgumentNullException>(
            () => agentFactory.CreateFromYamlAsync(SimpleAgent));
    }

    [Fact]
    public async Task CreateFromYamlAsync_NullText_ThrowsArgumentNullExceptionAsync()
    {
        // Arrange
        var agentFactory = new TestAgentFactory();

        // Act & Assert
        await Assert.ThrowsAsync<ArgumentNullException>(
            () => agentFactory.CreateFromYamlAsync(null!));
    }

    [Fact]
    public async Task CreateFromYamlAsync_EmptyText_ThrowsArgumentExceptionAsync()
    {
        // Arrange
        var agentFactory = new TestAgentFactory();

        // Act & Assert
        await Assert.ThrowsAsync<ArgumentException>(
            () => agentFactory.CreateFromYamlAsync(EmptyYaml));
    }

    [Fact]
    public async Task CreateFromYamlAsync_WhitespaceText_ThrowsArgumentExceptionAsync()
    {
        // Arrange
        var agentFactory = new TestAgentFactory();

        // Act & Assert
        await Assert.ThrowsAsync<ArgumentException>(
            () => agentFactory.CreateFromYamlAsync("   "));
    }

    [Fact]
    public async Task CreateFromYamlAsync_InvalidYaml_ThrowsExceptionAsync()
    {
        // Arrange
        var agentFactory = new TestAgentFactory();

        // Act & Assert
        await Assert.ThrowsAsync<InvalidDataException>(
            () => agentFactory.CreateFromYamlAsync(InvalidYaml));
    }

    [Fact]
    public async Task CreateFromYamlAsync_CancellationToken_PassedToFactoryAsync()
    {
        // Arrange
        var agentFactory = new TestAgentFactory();
        var cancellationToken = new CancellationToken(true);

        // Act & Assert
        await Assert.ThrowsAsync<OperationCanceledException>(
            () => agentFactory.CreateFromYamlAsync(SimpleAgent, cancellationToken: cancellationToken));
    }

    [Fact]
    public async Task CreateFromYamlAsync_UnsupportedAgentType_ThrowsNotSupportedExceptionAsync()
    {
        // Arrange
        var agentFactory = new TestAgentFactory(returnNull: true);

        // Act & Assert
        await Assert.ThrowsAsync<NotSupportedException>(
            () => agentFactory.CreateFromYamlAsync(SimpleAgent));
    }

    [Fact]
    public async Task CreateFromYamlAsync_FactoryThrows_PropagatesExceptionAsync()
    {
        // Arrange
        var agentFactory = new TestAgentFactory(shouldThrow: true);

        // Act & Assert
        await Assert.ThrowsAsync<InvalidOperationException>(
            () => agentFactory.CreateFromYamlAsync(SimpleAgent));
    }

    [Fact]
    public async Task CreateFromYamlAsync_OptionsPassedToFactoryAsync()
    {
        // Arrange
        var agentFactory = new TestAgentFactory();
        var options = new AgentCreationOptions();

        // Act
        await agentFactory.CreateFromYamlAsync(SimpleAgent, options);

        // Assert
        Assert.Same(options, agentFactory.LastUsedOptions);
    }

    [Fact]
    public async Task CreateFromYamlAsync_AgentDefinitionPassedToFactoryAsync()
    {
        // Arrange
        var agentFactory = new TestAgentFactory();

        // Act
        await agentFactory.CreateFromYamlAsync(SimpleAgent);

        // Assert
        Assert.NotNull(agentFactory.LastUsedAgentDefinition);
        Assert.Equal("TestAgent", agentFactory.LastUsedAgentDefinition.GetName());
    }

    /// <summary>
    /// Test implementation of AgentFactory for unit testing
    /// </summary>
    private sealed class TestAgentFactory : AgentFactory
    {
        private readonly bool _returnNull;
        private readonly bool _shouldThrow;

        public GptComponentMetadata? LastUsedAgentDefinition { get; private set; }
        public AgentCreationOptions? LastUsedOptions { get; private set; }

        public TestAgentFactory(bool returnNull = false, bool shouldThrow = false)
            : base(["chat_client_agent", "test_agent"])
        {
            this._returnNull = returnNull;
            this._shouldThrow = shouldThrow;
        }

        public override Task<AIAgent?> TryCreateAsync(
            GptComponentMetadata agentDefinition,
            AgentCreationOptions agentCreationOptions,
            CancellationToken cancellationToken = default)
        {
            cancellationToken.ThrowIfCancellationRequested();

            this.LastUsedAgentDefinition = agentDefinition;
            this.LastUsedOptions = agentCreationOptions;

            if (this._shouldThrow)
            {
                throw new InvalidOperationException("Test exception");
            }

            if (this._returnNull)
            {
                return Task.FromResult<AIAgent?>(null);
            }

            return Task.FromResult<AIAgent?>(new TestAgent());
        }
    }

    /// <summary>
    /// Test implementation of AIAgent for unit testing
    /// </summary>
    private sealed class TestAgent : AIAgent
    {
        public override string Name => "TestAgent";

        public override AgentThread GetNewThread() => new TestAgentThread();

        public override AgentThread DeserializeThread(JsonElement serializedThread, JsonSerializerOptions? jsonSerializerOptions = null)
            => new TestAgentThread();

        public override Task<AgentRunResponse> RunAsync(
            IEnumerable<ChatMessage> messages,
            AgentThread? thread = null,
            AgentRunOptions? options = null,
            CancellationToken cancellationToken = default)
        {
            return Task.FromResult(new AgentRunResponse
            {
                Messages = [new ChatMessage(ChatRole.Assistant, "Test response")]
            });
        }

        public override async IAsyncEnumerable<AgentRunResponseUpdate> RunStreamingAsync(
            IEnumerable<ChatMessage> messages,
            AgentThread? thread = null,
            AgentRunOptions? options = null,
            [EnumeratorCancellation] CancellationToken cancellationToken = default)
        {
            await Task.Yield();
            yield return new AgentRunResponseUpdate(ChatRole.Assistant, "Test response");
        }
    }

    /// <summary>
    /// Test implementation of AgentThread for unit testing
    /// </summary>
    private sealed class TestAgentThread : AgentThread
    {
        public override Task<JsonElement> SerializeAsync(JsonSerializerOptions? jsonSerializerOptions = null, CancellationToken cancellationToken = default)
        {
            return Task.FromResult(JsonSerializer.SerializeToElement(new { }));
        }
    }
}
