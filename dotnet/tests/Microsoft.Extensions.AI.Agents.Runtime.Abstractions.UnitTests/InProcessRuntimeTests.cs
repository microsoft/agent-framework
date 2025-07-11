// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;

namespace Microsoft.Extensions.AI.Agents.Runtime.InProcess.Tests;

public class InProcessRuntimeTests()
{
    [Fact]
    public async Task RuntimeStatusLifecycleTestAsync()
    {
        // Arrange & Act
        await using InProcessRuntime runtime = new();

        // Assert
        Assert.Equal(0, runtime.MessageCountForTesting);

        runtime.Start();

        // Assert
        // Invalid to start runtime that is already started
        Assert.Throws<InvalidOperationException>(runtime.Start);
        Assert.Equal(0, runtime.MessageCountForTesting);

        // Act
        await runtime.DisposeAsync();

        // Assert
        Assert.Equal(0, runtime.MessageCountForTesting);
    }

    [Fact]
    public async Task SubscriptionRegistrationLifecycleTestAsync()
    {
        // Arrange
        await using InProcessRuntime runtime = new();
        TestSubscription subscription = new("TestTopic", new("MyAgent"));

        // Act & Assert
        await Assert.ThrowsAsync<InvalidOperationException>(async () => await runtime.RemoveSubscriptionAsync(subscription.Id));

        // Arrange
        await runtime.AddSubscriptionAsync(subscription);

        // Act & Assert
        await Assert.ThrowsAsync<InvalidOperationException>(async () => await runtime.AddSubscriptionAsync(subscription));

        // Act
        await runtime.RemoveSubscriptionAsync(subscription.Id);
    }

    [Fact]
    public async Task AgentRegistrationLifecycleTestAsync()
    {
        // Arrange
        const string AgentType = "MyAgent";
        const string AgentDescription = "A test agent";
        List<MockAgent> agents = [];
        await using InProcessRuntime runtime = new();

        // Act & Assert
        await Assert.ThrowsAsync<InvalidOperationException>(async () => await runtime.GetActorAsync(AgentType, lazy: false));

        // Arrange
        await runtime.RegisterActorFactoryAsync(new(AgentType), factoryFunc);

        // Act & Assert
        await Assert.ThrowsAsync<InvalidOperationException>(async () => await runtime.RegisterActorFactoryAsync(new(AgentType), factoryFunc));

        // Act: Lookup by type
        ActorId agentId = await runtime.GetActorAsync(AgentType, lazy: false);

        // Assert
        Assert.Single(agents);
        Assert.Single(runtime._actorInstances);

        // Act
        MockAgent agent = await runtime.TryGetUnderlyingActorInstanceAsync<MockAgent>(agentId);

        // Assert
        Assert.Equal(agentId, agent.Id);

        // Act & Assert
        await Assert.ThrowsAsync<InvalidOperationException>(async () => await runtime.TryGetUnderlyingActorInstanceAsync<WrongAgent>(agentId));

        // Act: Lookup by ID
        ActorId sameId = await runtime.GetActorAsync(agentId, lazy: false);

        // Assert
        Assert.Equal(agentId, sameId);

        // Act: Lookup by Type
        sameId = await runtime.GetActorAsync((ActorType)agent.Id.Type, lazy: false);

        // Assert
        Assert.Equal(agentId, sameId);

        // Act: Lookup metadata
        ActorMetadata metadata = await runtime.GetActorMetadataAsync(agentId);

        // Assert
        Assert.Equal(agentId.Type, metadata.Type);
        Assert.Equal(AgentDescription, metadata.Description);
        Assert.Equal(agentId.Key, metadata.Key);

        // Act: Access proxy
        IdProxyActor? proxy = await runtime.TryGetActorProxyAsync(agentId);

        // Assert
        Assert.NotNull(proxy);
        Assert.Equal(agentId, proxy.Id);
        Assert.Equal(metadata.Type, proxy.Metadata.Type);
        Assert.Equal(metadata.Description, proxy.Metadata.Description);
        Assert.Equal(metadata.Key, proxy.Metadata.Key);

        async ValueTask<MockAgent> factoryFunc(ActorId id, IAgentRuntime runtime)
        {
            MockAgent agent = new(id, runtime, AgentDescription);
            agents.Add(agent);
            return agent;
        }
    }

    [Fact]
    public async Task AgentStateLifecycleTestAsync()
    {
        // Arrange
        const string AgentType = "MyAgent";
        const string TestMessage = "test message";

        await using InProcessRuntime firstRuntime = new();
        await firstRuntime.RegisterActorFactoryAsync(new(AgentType), factoryFunc);

        // Act
        ActorId agentId = await firstRuntime.GetActorAsync(AgentType, lazy: false);

        // Assert
        Assert.Single(firstRuntime._actorInstances);

        // Arrange
        MockAgent agent = (MockAgent)firstRuntime._actorInstances[agentId];
        agent.ReceivedMessages.Add(TestMessage);

        // Act
        JsonElement agentState = await firstRuntime.SaveActorStateAsync(agentId);

        // Arrange
        await using InProcessRuntime secondRuntime = new();
        await secondRuntime.RegisterActorFactoryAsync(new(AgentType), factoryFunc);

        // Act
        await secondRuntime.LoadActorStateAsync(agentId, agentState);

        // Assert
        Assert.Single(secondRuntime._actorInstances);
        MockAgent copy = (MockAgent)secondRuntime._actorInstances[agentId];
        Assert.Single(copy.ReceivedMessages);
        Assert.Equal(TestMessage, copy.ReceivedMessages.Single().ToString());

        static async ValueTask<MockAgent> factoryFunc(ActorId id, IAgentRuntime runtime)
        {
            MockAgent agent = new(id, runtime, "A test agent");
            return agent;
        }
    }

    [Fact]
    public async Task RuntimeSendMessageTestAsync()
    {
        // Arrange
        await using InProcessRuntime runtime = new();
        MockAgent? agent = null;
        await runtime.RegisterActorFactoryAsync(new("MyAgent"), async (id, runtime) =>
        {
            agent = new MockAgent(id, runtime, "A test agent");
            return agent;
        });

        // Act: Ensure the agent is actually created
        ActorId agentId = await runtime.GetActorAsync("MyAgent", lazy: false);

        // Assert
        Assert.NotNull(agent);
        Assert.Empty(agent.ReceivedMessages);

        // Act: Send message
        runtime.Start();
        await runtime.SendMessageAsync("TestMessage", agent.Id);
        await runtime.DisposeAsync();

        // Assert
        Assert.Equal(0, runtime.MessageCountForTesting);
        Assert.Single(agent.ReceivedMessages);
    }

    // Agent will not deliver to self
    [Fact]
    public async Task RuntimeAgentPublishToSelfTestAsync()
    {
        // Arrange
        await using InProcessRuntime runtime = new();

        MockAgent? agent = null;
        await runtime.RegisterActorFactoryAsync(new("MyAgent"), async (id, runtime) =>
        {
            agent = new MockAgent(id, runtime, "A test agent");
            return agent;
        });

        // Assert
        Assert.Empty(runtime._actorInstances);

        // Act: Ensure the agent is actually created
        ActorId agentId = await runtime.GetActorAsync("MyAgent", lazy: false);

        // Assert
        Assert.NotNull(agent);
        Assert.Single(runtime._actorInstances);

        const string TopicType = "TestTopic";

        // Arrange
        await runtime.AddSubscriptionAsync(new TestSubscription(TopicType, agentId.Type));

        // Act
        runtime.Start();
        await runtime.PublishMessageAsync("SelfMessage", new TopicId(TopicType), sender: agentId);
        await runtime.DisposeAsync();

        // Assert
        Assert.Empty(agent.ReceivedMessages);
    }

    [Fact]
    public async Task RuntimeShouldSaveLoadStateCorrectlyTestAsync()
    {
        // Arrange: Create a runtime and register an agent
        await using InProcessRuntime runtime = new();
        MockAgent? agent = null;
        await runtime.RegisterActorFactoryAsync(new("MyAgent"), async (id, runtime) =>
        {
            agent = new MockAgent(id, runtime, "test agent");
            return agent;
        });

        // Get agent ID and instantiate agent by publishing
        ActorId agentId = await runtime.GetActorAsync("MyAgent", lazy: false);
        const string TopicType = "TestTopic";
        await runtime.AddSubscriptionAsync(new TestSubscription(TopicType, agentId.Type));

        runtime.Start();
        await runtime.PublishMessageAsync("test", new TopicId(TopicType));
        await runtime.DisposeAsync();

        // Act: Save the state
        JsonElement savedState = await runtime.SaveStateAsync();

        // Assert: Ensure the agent's state is stored as a valid JSON type
        Assert.NotNull(agent);
        Assert.True(savedState.TryGetProperty(agentId.ToString(), out JsonElement agentState));
        Assert.Equal(JsonValueKind.Array, agentState.ValueKind);
        Assert.Single(agent.ReceivedMessages);

        // Arrange: Serialize and Deserialize the state to simulate persistence
        string json = JsonSerializer.Serialize(savedState);
        Assert.NotNull(json);
        Assert.NotEmpty(json);
        IDictionary<string, JsonElement> deserializedState = JsonSerializer.Deserialize<IDictionary<string, JsonElement>>(json)
            ?? throw new InvalidOperationException("Deserialized state is unexpectedly null");
        Assert.True(deserializedState.ContainsKey(agentId.ToString()));

        // Act: Start new runtime and restore the state
        agent = null;
        await using InProcessRuntime newRuntime = InProcessRuntime.StartNew();
        await newRuntime.RegisterActorFactoryAsync(new("MyAgent"), async (id, runtime) =>
        {
            agent = new MockAgent(id, runtime, "another agent");
            return agent;
        });

        // Assert: Show that no agent instances exist in the new runtime
        Assert.Empty(newRuntime._actorInstances);

        // Act: Load the state into the new runtime and show that agent is now instantiated
        await newRuntime.LoadStateAsync(savedState);

        // Assert
        Assert.NotNull(agent);
        Assert.Single(newRuntime._actorInstances);
        Assert.True(newRuntime._actorInstances.ContainsKey(agentId));
        Assert.Single(agent.ReceivedMessages);
    }

#pragma warning disable CA1812 // Avoid uninstantiated internal classes
    private sealed class WrongAgent : IRuntimeActor
#pragma warning restore CA1812
    {
        public ActorId Id => throw new NotImplementedException();

        public ActorMetadata Metadata => throw new NotImplementedException();

        public ValueTask LoadStateAsync(JsonElement state, CancellationToken cancellationToken = default)
        {
            throw new NotImplementedException();
        }

        public ValueTask<object?> OnMessageAsync(object message, MessageContext messageContext, CancellationToken cancellationToken = default)
        {
            throw new NotImplementedException();
        }

        public ValueTask<JsonElement> SaveStateAsync(CancellationToken cancellationToken = default)
        {
            throw new NotImplementedException();
        }
    }
}
