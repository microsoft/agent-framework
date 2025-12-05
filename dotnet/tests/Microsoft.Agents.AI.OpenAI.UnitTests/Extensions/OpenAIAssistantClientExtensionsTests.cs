// Copyright (c) Microsoft. All rights reserved.

#pragma warning disable CS0618 // Type or member is obsolete - This is intentional as we are testing deprecated methods

using System;
using System.ClientModel;
using System.ClientModel.Primitives;
using System.IO;
using System.Reflection;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using OpenAI;
using OpenAI.Assistants;

namespace Microsoft.Agents.AI.OpenAI.UnitTests.Extensions;

/// <summary>
/// Unit tests for the <see cref="OpenAIAssistantClientExtensions"/> class.
/// </summary>
public sealed class OpenAIAssistantClientExtensionsTests
{
    /// <summary>
    /// Verify that CreateAIAgent with clientFactory parameter correctly applies the factory.
    /// </summary>
    [Fact]
    public void CreateAIAgent_WithClientFactory_AppliesFactoryCorrectly()
    {
        // Arrange
        var assistantClient = new TestAssistantClient();
        var testChatClient = new TestChatClient(assistantClient.AsIChatClient("test-model"));
        const string ModelId = "test-model";

        // Act
        var agent = assistantClient.CreateAIAgent(
            ModelId,
            instructions: "Test instructions",
            name: "Test Agent",
            description: "Test description",
            clientFactory: (innerClient) => testChatClient);

        // Assert
        Assert.NotNull(agent);
        Assert.Equal("Test Agent", agent.Name);
        Assert.Equal("Test description", agent.Description);

        // Verify that the custom chat client can be retrieved from the agent's service collection
        var retrievedTestClient = agent.GetService<TestChatClient>();
        Assert.NotNull(retrievedTestClient);
        Assert.Same(testChatClient, retrievedTestClient);
    }

    /// <summary>
    /// Verify that CreateAIAgent with clientFactory using AsBuilder pattern works correctly.
    /// </summary>
    [Fact]
    public void CreateAIAgent_WithClientFactoryUsingAsBuilder_AppliesFactoryCorrectly()
    {
        // Arrange
        var assistantClient = new TestAssistantClient();
        TestChatClient? testChatClient = null;

        const string ModelId = "test-model";

        // Act
        var agent = assistantClient.CreateAIAgent(
            ModelId,
            instructions: "Test instructions",
            clientFactory: (innerClient) =>
                innerClient.AsBuilder()
                    .Use((innerClient) => testChatClient = new TestChatClient(innerClient))
                .Build());

        // Assert
        Assert.NotNull(agent);

        // Verify that the custom chat client can be retrieved from the agent's service collection
        var retrievedTestClient = agent.GetService<TestChatClient>();
        Assert.NotNull(retrievedTestClient);
        Assert.Same(testChatClient, retrievedTestClient);
    }

    /// <summary>
    /// Verify that CreateAIAgent with options and clientFactory parameter correctly applies the factory.
    /// </summary>
    [Fact]
    public void CreateAIAgent_WithOptionsAndClientFactory_AppliesFactoryCorrectly()
    {
        // Arrange
        var assistantClient = new TestAssistantClient();
        var testChatClient = new TestChatClient(assistantClient.AsIChatClient("test-model"));
        const string ModelId = "test-model";
        var options = new ChatClientAgentOptions
        {
            Name = "Test Agent",
            Description = "Test description",
            ChatOptions = new() { Instructions = "Test instructions" }
        };

        // Act
        var agent = assistantClient.CreateAIAgent(
            ModelId,
            options,
            clientFactory: (innerClient) => testChatClient);

        // Assert
        Assert.NotNull(agent);
        Assert.Equal("Test Agent", agent.Name);
        Assert.Equal("Test description", agent.Description);

        // Verify that the custom chat client can be retrieved from the agent's service collection
        var retrievedTestClient = agent.GetService<TestChatClient>();
        Assert.NotNull(retrievedTestClient);
        Assert.Same(testChatClient, retrievedTestClient);
    }

    /// <summary>
    /// Verify that CreateAIAgent without clientFactory works normally.
    /// </summary>
    [Fact]
    public void CreateAIAgent_WithoutClientFactory_WorksNormally()
    {
        // Arrange
        var assistantClient = new TestAssistantClient();
        const string ModelId = "test-model";

        // Act
        var agent = assistantClient.CreateAIAgent(
            ModelId,
            instructions: "Test instructions",
            name: "Test Agent");

        // Assert
        Assert.NotNull(agent);
        Assert.Equal("Test Agent", agent.Name);

        // Verify that no TestChatClient is available since no factory was provided
        var retrievedTestClient = agent.GetService<TestChatClient>();
        Assert.Null(retrievedTestClient);
    }

    /// <summary>
    /// Verify that CreateAIAgent with null clientFactory works normally.
    /// </summary>
    [Fact]
    public void CreateAIAgent_WithNullClientFactory_WorksNormally()
    {
        // Arrange
        var assistantClient = new TestAssistantClient();
        const string ModelId = "test-model";

        // Act
        var agent = assistantClient.CreateAIAgent(
            ModelId,
            instructions: "Test instructions",
            name: "Test Agent",
            clientFactory: null);

        // Assert
        Assert.NotNull(agent);
        Assert.Equal("Test Agent", agent.Name);

        // Verify that no TestChatClient is available since no factory was provided
        var retrievedTestClient = agent.GetService<TestChatClient>();
        Assert.Null(retrievedTestClient);
    }

    /// <summary>
    /// Verify that CreateAIAgent throws ArgumentNullException when client is null.
    /// </summary>
    [Fact]
    public void CreateAIAgent_WithNullClient_ThrowsArgumentNullException()
    {
        // Act & Assert
        var exception = Assert.Throws<ArgumentNullException>(() =>
            ((AssistantClient)null!).CreateAIAgent("test-model"));

        Assert.Equal("client", exception.ParamName);
    }

    /// <summary>
    /// Verify that CreateAIAgent throws ArgumentNullException when model is null.
    /// </summary>
    [Fact]
    public void CreateAIAgent_WithNullModel_ThrowsArgumentNullException()
    {
        // Arrange
        var assistantClient = new TestAssistantClient();

        // Act & Assert
        var exception = Assert.Throws<ArgumentNullException>(() =>
            assistantClient.CreateAIAgent(null!));

        Assert.Equal("model", exception.ParamName);
    }

    /// <summary>
    /// Verify that CreateAIAgent with options throws ArgumentNullException when options is null.
    /// </summary>
    [Fact]
    public void CreateAIAgent_WithNullOptions_ThrowsArgumentNullException()
    {
        // Arrange
        var assistantClient = new TestAssistantClient();

        // Act & Assert
        var exception = Assert.Throws<ArgumentNullException>(() =>
            assistantClient.CreateAIAgent("test-model", (ChatClientAgentOptions)null!));

        Assert.Equal("options", exception.ParamName);
    }

    /// <summary>
    /// Verify that GetAIAgent with ClientResult and options works correctly.
    /// </summary>
    [Fact]
    public void GetAIAgent_WithClientResultAndOptions_WorksCorrectly()
    {
        // Arrange
        var assistantClient = new TestAssistantClient();
        var assistant = ModelReaderWriter.Read<Assistant>(BinaryData.FromString("""{"id": "asst_abc123", "name": "Original Name", "description": "Original Description", "instructions": "Original Instructions"}"""))!;
        var clientResult = ClientResult.FromValue(assistant, new FakePipelineResponse());

        var options = new ChatClientAgentOptions
        {
            Name = "Override Name",
            Description = "Override Description",
            ChatOptions = new() { Instructions = "Override Instructions" }
        };

        // Act
        var agent = assistantClient.GetAIAgent(clientResult, options);

        // Assert
        Assert.NotNull(agent);
        Assert.Equal("Override Name", agent.Name);
        Assert.Equal("Override Description", agent.Description);
        Assert.Equal("Override Instructions", agent.Instructions);
    }

    /// <summary>
    /// Verify that GetAIAgent with Assistant and options works correctly.
    /// </summary>
    [Fact]
    public void GetAIAgent_WithAssistantAndOptions_WorksCorrectly()
    {
        // Arrange
        var assistantClient = new TestAssistantClient();
        var assistant = ModelReaderWriter.Read<Assistant>(BinaryData.FromString("""{"id": "asst_abc123", "name": "Original Name", "description": "Original Description", "instructions": "Original Instructions"}"""))!;

        var options = new ChatClientAgentOptions
        {
            Name = "Override Name",
            Description = "Override Description",
            ChatOptions = new() { Instructions = "Override Instructions" }
        };

        // Act
        var agent = assistantClient.GetAIAgent(assistant, options);

        // Assert
        Assert.NotNull(agent);
        Assert.Equal("Override Name", agent.Name);
        Assert.Equal("Override Description", agent.Description);
        Assert.Equal("Override Instructions", agent.Instructions);
    }

    /// <summary>
    /// Verify that GetAIAgent with Assistant and options falls back to assistant metadata when options are null.
    /// </summary>
    [Fact]
    public void GetAIAgent_WithAssistantAndOptionsWithNullFields_FallsBackToAssistantMetadata()
    {
        // Arrange
        var assistantClient = new TestAssistantClient();
        var assistant = ModelReaderWriter.Read<Assistant>(BinaryData.FromString("""{"id": "asst_abc123", "name": "Original Name", "description": "Original Description", "instructions": "Original Instructions"}"""))!;

        var options = new ChatClientAgentOptions(); // Empty options

        // Act
        var agent = assistantClient.GetAIAgent(assistant, options);

        // Assert
        Assert.NotNull(agent);
        Assert.Equal("Original Name", agent.Name);
        Assert.Equal("Original Description", agent.Description);
        Assert.Equal("Original Instructions", agent.Instructions);
    }

    /// <summary>
    /// Verify that GetAIAgent with agentId and options works correctly.
    /// </summary>
    [Fact]
    public void GetAIAgent_WithAgentIdAndOptions_WorksCorrectly()
    {
        // Arrange
        var assistantClient = new TestAssistantClient();
        const string AgentId = "asst_abc123";

        var options = new ChatClientAgentOptions
        {
            Name = "Override Name",
            Description = "Override Description",
            ChatOptions = new() { Instructions = "Override Instructions" }
        };

        // Act
        var agent = assistantClient.GetAIAgent(AgentId, options);

        // Assert
        Assert.NotNull(agent);
        Assert.Equal("Override Name", agent.Name);
        Assert.Equal("Override Description", agent.Description);
        Assert.Equal("Override Instructions", agent.Instructions);
    }

    /// <summary>
    /// Verify that GetAIAgentAsync with agentId and options works correctly.
    /// </summary>
    [Fact]
    public async Task GetAIAgentAsync_WithAgentIdAndOptions_WorksCorrectlyAsync()
    {
        // Arrange
        var assistantClient = new TestAssistantClient();
        const string AgentId = "asst_abc123";

        var options = new ChatClientAgentOptions
        {
            Name = "Override Name",
            Description = "Override Description",
            ChatOptions = new() { Instructions = "Override Instructions" }
        };

        // Act
        var agent = await assistantClient.GetAIAgentAsync(AgentId, options);

        // Assert
        Assert.NotNull(agent);
        Assert.Equal("Override Name", agent.Name);
        Assert.Equal("Override Description", agent.Description);
        Assert.Equal("Override Instructions", agent.Instructions);
    }

    /// <summary>
    /// Verify that GetAIAgent with clientFactory parameter correctly applies the factory.
    /// </summary>
    [Fact]
    public void GetAIAgent_WithClientFactory_AppliesFactoryCorrectly()
    {
        // Arrange
        var assistantClient = new TestAssistantClient();
        var assistant = ModelReaderWriter.Read<Assistant>(BinaryData.FromString("""{"id": "asst_abc123", "name": "Test Agent"}"""))!;
        var testChatClient = new TestChatClient(assistantClient.AsIChatClient("asst_abc123"));

        var options = new ChatClientAgentOptions
        {
            Name = "Test Agent"
        };

        // Act
        var agent = assistantClient.GetAIAgent(
            assistant,
            options,
            clientFactory: (innerClient) => testChatClient);

        // Assert
        Assert.NotNull(agent);
        Assert.Equal("Test Agent", agent.Name);

        // Verify that the custom chat client can be retrieved from the agent's service collection
        var retrievedTestClient = agent.GetService<TestChatClient>();
        Assert.NotNull(retrievedTestClient);
        Assert.Same(testChatClient, retrievedTestClient);
    }

    /// <summary>
    /// Verify that GetAIAgent throws ArgumentNullException when assistantClientResult is null.
    /// </summary>
    [Fact]
    public void GetAIAgent_WithNullClientResult_ThrowsArgumentNullException()
    {
        // Arrange
        var assistantClient = new TestAssistantClient();
        var options = new ChatClientAgentOptions();

        // Act & Assert
        var exception = Assert.Throws<ArgumentNullException>(() =>
            assistantClient.GetAIAgent((ClientResult<Assistant>)null!, options));

        Assert.Equal("assistantClientResult", exception.ParamName);
    }

    /// <summary>
    /// Verify that GetAIAgent throws ArgumentNullException when assistant is null.
    /// </summary>
    [Fact]
    public void GetAIAgent_WithNullAssistant_ThrowsArgumentNullException()
    {
        // Arrange
        var assistantClient = new TestAssistantClient();
        var options = new ChatClientAgentOptions();

        // Act & Assert
        var exception = Assert.Throws<ArgumentNullException>(() =>
            assistantClient.GetAIAgent((Assistant)null!, options));

        Assert.Equal("assistantMetadata", exception.ParamName);
    }

    /// <summary>
    /// Verify that GetAIAgent throws ArgumentNullException when options is null.
    /// </summary>
    [Fact]
    public void GetAIAgent_WithNullOptions_ThrowsArgumentNullException()
    {
        // Arrange
        var assistantClient = new TestAssistantClient();
        var assistant = ModelReaderWriter.Read<Assistant>(BinaryData.FromString("""{"id": "asst_abc123"}"""))!;

        // Act & Assert
        var exception = Assert.Throws<ArgumentNullException>(() =>
            assistantClient.GetAIAgent(assistant, (ChatClientAgentOptions)null!));

        Assert.Equal("options", exception.ParamName);
    }

    /// <summary>
    /// Verify that GetAIAgent throws ArgumentException when agentId is empty.
    /// </summary>
    [Fact]
    public void GetAIAgent_WithEmptyAgentId_ThrowsArgumentException()
    {
        // Arrange
        var assistantClient = new TestAssistantClient();
        var options = new ChatClientAgentOptions();

        // Act & Assert
        var exception = Assert.Throws<ArgumentException>(() =>
            assistantClient.GetAIAgent(string.Empty, options));

        Assert.Equal("agentId", exception.ParamName);
    }

    /// <summary>
    /// Verify that GetAIAgentAsync throws ArgumentException when agentId is empty.
    /// </summary>
    [Fact]
    public async Task GetAIAgentAsync_WithEmptyAgentId_ThrowsArgumentExceptionAsync()
    {
        // Arrange
        var assistantClient = new TestAssistantClient();
        var options = new ChatClientAgentOptions();

        // Act & Assert
        var exception = await Assert.ThrowsAsync<ArgumentException>(() =>
            assistantClient.GetAIAgentAsync(string.Empty, options));

        Assert.Equal("agentId", exception.ParamName);
    }

    /// <summary>
    /// Verify that CreateAIAgent with services parameter correctly passes it through to the ChatClientAgent.
    /// </summary>
    [Fact]
    public void CreateAIAgent_WithServices_PassesServicesToAgent()
    {
        // Arrange
        var assistantClient = new TestAssistantClient();
        var serviceProvider = new TestServiceProvider();
        const string ModelId = "test-model";

        // Act
        var agent = assistantClient.CreateAIAgent(
            ModelId,
            instructions: "Test instructions",
            name: "Test Agent",
            services: serviceProvider);

        // Assert
        Assert.NotNull(agent);

        // Verify the IServiceProvider was passed through to the FunctionInvokingChatClient
        var chatClient = agent.GetService<IChatClient>();
        Assert.NotNull(chatClient);
        var functionInvokingClient = chatClient.GetService<FunctionInvokingChatClient>();
        Assert.NotNull(functionInvokingClient);
        Assert.Same(serviceProvider, GetFunctionInvocationServices(functionInvokingClient));
    }

    /// <summary>
    /// Verify that CreateAIAgent with options and services parameter correctly passes it through to the ChatClientAgent.
    /// </summary>
    [Fact]
    public void CreateAIAgent_WithOptionsAndServices_PassesServicesToAgent()
    {
        // Arrange
        var assistantClient = new TestAssistantClient();
        var serviceProvider = new TestServiceProvider();
        const string ModelId = "test-model";
        var options = new ChatClientAgentOptions
        {
            Name = "Test Agent",
            ChatOptions = new() { Instructions = "Test instructions" }
        };

        // Act
        var agent = assistantClient.CreateAIAgent(ModelId, options, services: serviceProvider);

        // Assert
        Assert.NotNull(agent);
        Assert.Equal("Test Agent", agent.Name);

        // Verify the IServiceProvider was passed through to the FunctionInvokingChatClient
        var chatClient = agent.GetService<IChatClient>();
        Assert.NotNull(chatClient);
        var functionInvokingClient = chatClient.GetService<FunctionInvokingChatClient>();
        Assert.NotNull(functionInvokingClient);
        Assert.Same(serviceProvider, GetFunctionInvocationServices(functionInvokingClient));
    }

    /// <summary>
    /// Verify that GetAIAgent with services parameter correctly passes it through to the ChatClientAgent.
    /// </summary>
    [Fact]
    public void GetAIAgent_WithServices_PassesServicesToAgent()
    {
        // Arrange
        var assistantClient = new TestAssistantClient();
        var serviceProvider = new TestServiceProvider();
        var assistant = ModelReaderWriter.Read<Assistant>(BinaryData.FromString("""{"id": "asst_abc123", "name": "Test Agent"}"""))!;

        // Act
        var agent = assistantClient.GetAIAgent(assistant, services: serviceProvider);

        // Assert
        Assert.NotNull(agent);

        // Verify the IServiceProvider was passed through to the FunctionInvokingChatClient
        var chatClient = agent.GetService<IChatClient>();
        Assert.NotNull(chatClient);
        var functionInvokingClient = chatClient.GetService<FunctionInvokingChatClient>();
        Assert.NotNull(functionInvokingClient);
        Assert.Same(serviceProvider, GetFunctionInvocationServices(functionInvokingClient));
    }

    /// <summary>
    /// Verify that GetAIAgentAsync with services parameter correctly passes it through to the ChatClientAgent.
    /// </summary>
    [Fact]
    public async Task GetAIAgentAsync_WithServices_PassesServicesToAgentAsync()
    {
        // Arrange
        var assistantClient = new TestAssistantClient();
        var serviceProvider = new TestServiceProvider();

        // Act
        var agent = await assistantClient.GetAIAgentAsync("asst_abc123", services: serviceProvider);

        // Assert
        Assert.NotNull(agent);

        // Verify the IServiceProvider was passed through to the FunctionInvokingChatClient
        var chatClient = agent.GetService<IChatClient>();
        Assert.NotNull(chatClient);
        var functionInvokingClient = chatClient.GetService<FunctionInvokingChatClient>();
        Assert.NotNull(functionInvokingClient);
        Assert.Same(serviceProvider, GetFunctionInvocationServices(functionInvokingClient));
    }

    /// <summary>
    /// Verify that CreateAIAgent with both clientFactory and services works correctly.
    /// </summary>
    [Fact]
    public void CreateAIAgent_WithClientFactoryAndServices_AppliesBothCorrectly()
    {
        // Arrange
        var assistantClient = new TestAssistantClient();
        var serviceProvider = new TestServiceProvider();
        var testChatClient = new TestChatClient(assistantClient.AsIChatClient("test-model"));
        const string ModelId = "test-model";

        // Act
        var agent = assistantClient.CreateAIAgent(
            ModelId,
            instructions: "Test instructions",
            name: "Test Agent",
            clientFactory: (innerClient) => testChatClient,
            services: serviceProvider);

        // Assert
        Assert.NotNull(agent);

        // Verify the custom chat client was applied
        var retrievedTestClient = agent.GetService<TestChatClient>();
        Assert.NotNull(retrievedTestClient);
        Assert.Same(testChatClient, retrievedTestClient);

        // Verify the IServiceProvider was passed through
        var chatClient = agent.GetService<IChatClient>();
        Assert.NotNull(chatClient);
        var functionInvokingClient = chatClient.GetService<FunctionInvokingChatClient>();
        Assert.NotNull(functionInvokingClient);
        Assert.Same(serviceProvider, GetFunctionInvocationServices(functionInvokingClient));
    }

    /// <summary>
    /// Uses reflection to access the FunctionInvocationServices property which is not public.
    /// </summary>
    private static IServiceProvider? GetFunctionInvocationServices(FunctionInvokingChatClient client)
    {
        var property = typeof(FunctionInvokingChatClient).GetProperty(
            "FunctionInvocationServices",
            BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic);
        return property?.GetValue(client) as IServiceProvider;
    }

    /// <summary>
    /// Creates a test AssistantClient implementation for testing.
    /// </summary>
    private sealed class TestAssistantClient : AssistantClient
    {
        public TestAssistantClient()
        {
        }

        public override ClientResult<Assistant> CreateAssistant(string model, AssistantCreationOptions? options = null, CancellationToken cancellationToken = default)
        {
            return ClientResult.FromValue(ModelReaderWriter.Read<Assistant>(BinaryData.FromString("""{"id": "asst_abc123"}""")), new FakePipelineResponse())!;
        }

        public override ClientResult<Assistant> GetAssistant(string assistantId, CancellationToken cancellationToken = default)
        {
            return ClientResult.FromValue(ModelReaderWriter.Read<Assistant>(BinaryData.FromString("""{"id": "asst_abc123", "name": "Original Name", "description": "Original Description", "instructions": "Original Instructions"}""")), new FakePipelineResponse())!;
        }

        public override async Task<ClientResult<Assistant>> GetAssistantAsync(string assistantId, CancellationToken cancellationToken = default)
        {
            await Task.Delay(1, cancellationToken); // Simulate async operation
            return ClientResult.FromValue(ModelReaderWriter.Read<Assistant>(BinaryData.FromString("""{"id": "asst_abc123", "name": "Original Name", "description": "Original Description", "instructions": "Original Instructions"}""")), new FakePipelineResponse())!;
        }
    }

    private sealed class TestChatClient : DelegatingChatClient
    {
        public TestChatClient(IChatClient innerClient) : base(innerClient)
        {
        }
    }

    private sealed class TestServiceProvider : IServiceProvider
    {
        public object? GetService(Type serviceType) => null;
    }

    private sealed class FakePipelineResponse : PipelineResponse
    {
        public override int Status => throw new NotImplementedException();

        public override string ReasonPhrase => throw new NotImplementedException();

        public override Stream? ContentStream { get => throw new NotImplementedException(); set => throw new NotImplementedException(); }

        public override BinaryData Content => throw new NotImplementedException();

        protected override PipelineResponseHeaders HeadersCore => throw new NotImplementedException();

        public override BinaryData BufferContent(CancellationToken cancellationToken = default)
        {
            throw new NotImplementedException();
        }

        public override ValueTask<BinaryData> BufferContentAsync(CancellationToken cancellationToken = default)
        {
            throw new NotImplementedException();
        }

        public override void Dispose()
        {
            throw new NotImplementedException();
        }
    }
}
