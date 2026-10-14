// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Azure.Cosmos;
using Microsoft.Extensions.AI;
using Moq;
using Moq.Protected;
using Newtonsoft.Json.Linq;

namespace Microsoft.Agents.AI.CosmosNoSql.UnitTests;

public sealed class CosmosChatHistoryProviderPartitionKeyTests
{
    [Theory]
    [InlineData(null, null, false)]
    [InlineData("tenant", null, false)]
    [InlineData(null, "user", false)]
    [InlineData("tenant", "user", false)]
    [InlineData("tenant", "user", true)]
    public async Task InvokedAsync_PersistsMetadata_IndependentlyOfPartitionKeyAsync(string? tenantId, string? userId, bool useCustomKey)
    {
        // Arrange
        var container = new Mock<Container>();
        var client = new Mock<CosmosClient>();
        client.SetupGet(c => c.ClientOptions).Returns(new CosmosClientOptions());
        client.Setup(c => c.GetContainer("database", "container")).Returns(container.Object);
        var state = new CosmosChatHistoryProvider.State("conversation", tenantId, userId);
        var options = new CosmosChatHistoryProviderOptions
        {
            StateKey = "custom-state",
            PartitionKeyFactory = useCustomKey ? s => new PartitionKey(s.ConversationId) : null
        };
        using var provider = new CosmosChatHistoryProvider(client.Object, "database", "container", _ => state, options);
        var context = new ChatHistoryProvider.InvokedContext(
            new Mock<AIAgent>().Object, new Mock<AgentSession>().Object, [new ChatMessage(ChatRole.User, "Hello")], []);

        // Act
        await provider.InvokedAsync(context);

        // Assert
        var invocation = Assert.Single(container.Invocations);
        var expectedKey = !useCustomKey && tenantId is not null && userId is not null
            ? new PartitionKeyBuilder().Add(tenantId).Add(userId).Add(state.ConversationId).Build()
            : new PartitionKey(state.ConversationId);
        Assert.Equal(expectedKey, invocation.Arguments[1]);
        var document = JObject.FromObject(invocation.Arguments[0]);
        Assert.Equal(tenantId, (string?)document["tenantId"]);
        Assert.Equal(userId, (string?)document["userId"]);
        Assert.Equal(state.ConversationId, (string?)document["sessionId"]);
        Assert.Equal(state.ConversationId, (string?)document["conversationId"]);
        Assert.Equal("custom-state", Assert.Single(provider.StateKeys));
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task InvokedAsync_CustomPartitionKey_IsUsedForTransactionalBatchAsync(bool useFlatKey)
    {
        // Arrange
        var container = new Mock<Container>();
        var client = new Mock<CosmosClient>();
        client.SetupGet(c => c.ClientOptions).Returns(new CosmosClientOptions());
        client.Setup(c => c.GetContainer("database", "container")).Returns(container.Object);
        var key = new PartitionKey(useFlatKey ? "conversation" : "tenant");
        var batch = new Mock<TransactionalBatch>();
        var response = new Mock<TransactionalBatchResponse>();
        response.SetupGet(r => r.IsSuccessStatusCode).Returns(true);
        batch.Setup(b => b.ExecuteAsync(It.IsAny<CancellationToken>())).ReturnsAsync(response.Object);
        container.Setup(c => c.CreateTransactionalBatch(key)).Returns(batch.Object);
        using var provider = new CosmosChatHistoryProvider(client.Object, "database", "container",
            _ => new CosmosChatHistoryProvider.State("conversation", "tenant", "user"),
            new CosmosChatHistoryProviderOptions { PartitionKeyFactory = s => new PartitionKey(useFlatKey ? s.ConversationId : s.TenantId) });
        var context = new ChatHistoryProvider.InvokedContext(
            new Mock<AIAgent>().Object, new Mock<AgentSession>().Object,
            [new ChatMessage(ChatRole.User, "Hello"), new ChatMessage(ChatRole.User, "World")], []);

        // Act
        await provider.InvokedAsync(context);

        // Assert
        container.Verify(c => c.CreateTransactionalBatch(key), Times.Once);
        var documents = batch.Invocations.Where(i => i.Method.Name == nameof(TransactionalBatch.CreateItem)).ToList();
        Assert.Equal(2, documents.Count);
        Assert.All(documents, invocation =>
        {
            var document = JObject.FromObject(invocation.Arguments[0]);
            Assert.Equal("tenant", (string?)document["tenantId"]);
            Assert.Equal("user", (string?)document["userId"]);
            Assert.Equal("conversation", (string?)document["sessionId"]);
        });
    }

    [Theory]
    [InlineData("retrieve")]
    [InlineData("count")]
    [InlineData("clear")]
    public async Task ReadOperations_InvokeCustomPartitionKeyFactoryAsync(string operation)
    {
        // Arrange
        var client = new Mock<CosmosClient>();
        client.SetupGet(c => c.ClientOptions).Returns(new CosmosClientOptions());
        client.Setup(c => c.GetContainer("database", "container")).Returns(new Mock<Container>().Object);
        var state = new CosmosChatHistoryProvider.State("conversation", "tenant", "user");
        var expectedException = new InvalidOperationException("Custom partition key factory");
        CosmosChatHistoryProvider.State? observedState = null;
        using var provider = new CosmosChatHistoryProvider(client.Object, "database", "container", _ => state,
            new CosmosChatHistoryProviderOptions
            {
                PartitionKeyFactory = s =>
                {
                    observedState = s;
                    throw expectedException;
                }
            });

        // Act
        var exception = await Assert.ThrowsAsync<InvalidOperationException>(async () =>
        {
            switch (operation)
            {
                case "retrieve":
                    await provider.GetMessagesAsync(null);
                    break;
                case "count":
                    await provider.GetMessageCountAsync(null);
                    break;
                case "clear":
                    await provider.ClearMessagesAsync(null);
                    break;
            }
        });

        // Assert
        Assert.Same(expectedException, exception);
        Assert.Same(state, observedState);
    }

    [Fact]
    public async Task InvokedAsync_AppliesStorageFiltersFromOptionsAsync()
    {
        // Arrange
        var container = new Mock<Container>();
        var client = new Mock<CosmosClient>();
        client.SetupGet(c => c.ClientOptions).Returns(new CosmosClientOptions());
        client.Setup(c => c.GetContainer("database", "container")).Returns(container.Object);
        using var provider = new CosmosChatHistoryProvider(client.Object, "database", "container",
            _ => new CosmosChatHistoryProvider.State("conversation"),
            new CosmosChatHistoryProviderOptions
            {
                StoreInputRequestMessageFilter = messages => messages.Where(m => m.Text == "Keep"),
                StoreInputResponseMessageFilter = _ => []
            });
        var context = new ChatHistoryProvider.InvokedContext(
            new Mock<AIAgent>().Object, new Mock<AgentSession>().Object,
            [new ChatMessage(ChatRole.User, "Keep"), new ChatMessage(ChatRole.User, "Discard")],
            [new ChatMessage(ChatRole.Assistant, "Discard response")]);

        // Act
        await provider.InvokedAsync(context);

        // Assert
        var invocation = Assert.Single(container.Invocations);
        var document = JObject.FromObject(invocation.Arguments[0]);
        Assert.Contains("Keep", (string)document["message"]!);
        Assert.DoesNotContain("Discard", (string)document["message"]!);
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public void Dispose_RespectsClientOwnershipOption(bool ownsClient)
    {
        // Arrange
        var client = new Mock<CosmosClient>();
        client.SetupGet(c => c.ClientOptions).Returns(new CosmosClientOptions());
        client.Setup(c => c.GetContainer("database", "container")).Returns(new Mock<Container>().Object);
        var provider = new CosmosChatHistoryProvider(client.Object, "database", "container",
            _ => new CosmosChatHistoryProvider.State("conversation"),
            new CosmosChatHistoryProviderOptions { OwnsClient = ownsClient });

        // Act
        provider.Dispose();

        // Assert
        client.Protected().Verify("Dispose", ownsClient ? Times.Once() : Times.Never(), new object[] { true });
    }
}
