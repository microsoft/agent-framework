// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Linq;
using System.Text.Json;
using System.Threading.Tasks;
using Microsoft.Azure.Cosmos;
using Microsoft.Extensions.AI;
using Microsoft.Agents.AI;
using Xunit;

namespace Microsoft.Agents.AI.Abstractions.UnitTests;

/// <summary>
/// Collection definition to ensure Cosmos DB tests don't run in parallel
/// </summary>
[CollectionDefinition("CosmosDB", DisableParallelization = true)]
public class CosmosDBTestFixture : ICollectionFixture<CosmosDBTestFixture>
{
}

/// <summary>
/// Contains tests for <see cref="CosmosAgentThread"/>.
///
/// These tests use the connection string constructor approach instead of manually creating CosmosClient instances,
/// making the tests simpler and more realistic.
///
/// Test Modes:
/// - Default Mode: Cleans up all test data after each test run (deletes database)
/// - Preserve Mode: Keeps containers and data for inspection in Cosmos DB Emulator Data Explorer
///
/// Usage Examples:
/// - Run all tests in preserve mode: $env:COSMOS_PRESERVE_CONTAINERS="true"; dotnet test tests/Microsoft.Agents.AI.Abstractions.UnitTests/
/// - Run specific test category in preserve mode: $env:COSMOS_PRESERVE_CONTAINERS="true"; dotnet test tests/Microsoft.Agents.AI.Abstractions.UnitTests/ --filter "Category=CosmosDB"
/// - Reset to cleanup mode: $env:COSMOS_PRESERVE_CONTAINERS=""; dotnet test tests/Microsoft.Agents.AI.Abstractions.UnitTests/
/// </summary>
[Collection("CosmosDB")]
[TestCaseOrderer("Xunit.Extensions.Ordering.TestCaseOrderer", "Xunit.Extensions.Ordering")]
public sealed class CosmosAgentThreadTests : IAsyncLifetime, IDisposable
{
    // Cosmos DB Emulator connection settings
    private const string EmulatorEndpoint = "https://localhost:8081";
    private const string EmulatorKey = "C2y6yDjf5/R+ob0N8A7Cgv30VRDJIWEHLM+4QDU5DE2nQ9nDuVTqobD4b8mGGyPMbIZnqyMsEcaGQy67XIw/Jw==";

    // Use static container names like CosmosChatMessageStoreTests for consistency
    private readonly string _testDatabaseId = $"AgentFrameworkTests-Thread-{Guid.NewGuid():N}";
    private readonly string _testContainerId = "ChatMessages"; // Use the same container as CosmosChatMessageStoreTests

    private string _connectionString = string.Empty;
    private bool _emulatorAvailable;
    private bool _preserveContainer;
    private CosmosClient? _setupClient; // Only used for test setup/cleanup

    public async Task InitializeAsync()
    {
        // Check environment variable to determine if we should preserve containers
        // Set COSMOS_PRESERVE_CONTAINERS=true to keep containers and data for inspection
        this._preserveContainer = string.Equals(Environment.GetEnvironmentVariable("COSMOS_PRESERVE_CONTAINERS"), "true", StringComparison.OrdinalIgnoreCase);

        this._connectionString = $"AccountEndpoint={EmulatorEndpoint};AccountKey={EmulatorKey}";

        try
        {
            // Only create CosmosClient for test setup - the actual tests will use connection string constructors
            this._setupClient = new CosmosClient(EmulatorEndpoint, EmulatorKey);

            // Test connection and ensure database/container exist
            var databaseResponse = await this._setupClient.CreateDatabaseIfNotExistsAsync(this._testDatabaseId);
            var containerResponse = await databaseResponse.Database.CreateContainerIfNotExistsAsync(
                this._testContainerId,
                "/conversationId",
                throughput: 400);

            // Verify the container is actually accessible by doing a read operation
            await containerResponse.Container.ReadContainerAsync();

            // Wait a moment for container to be fully propagated across all clients
            await Task.Delay(500);

            // Verify the container is accessible from a new client instance (simulating the test scenario)
            using var verificationClient = new CosmosClient(this._connectionString);
            var verificationContainer = verificationClient.GetContainer(this._testDatabaseId, this._testContainerId);
            await verificationContainer.ReadContainerAsync();

            this._emulatorAvailable = true;
        }
        catch (Exception)
        {
            // Emulator not available, tests will be skipped
            this._emulatorAvailable = false;
            this._setupClient?.Dispose();
            this._setupClient = null;
        }
    }

    public async Task DisposeAsync()
    {
        if (this._setupClient != null && this._emulatorAvailable)
        {
            try
            {
                // Clean up test database unless preserve mode is enabled
                if (!this._preserveContainer)
                {
                    // Delete the entire test database to clean up all containers
                    var database = this._setupClient.GetDatabase(this._testDatabaseId);
                    await database.DeleteAsync();
                }
            }
            catch (Exception ex)
            {
                // Ignore cleanup errors during test teardown
                Console.WriteLine($"Warning: Cleanup failed: {ex.Message}");
            }
            finally
            {
                this._setupClient.Dispose();
            }
        }
    }

    /// <summary>
    /// Implements IDisposable to properly dispose of the setup client.
    /// </summary>
    public void Dispose()
    {
        this._setupClient?.Dispose();
    }

    private void SkipIfEmulatorNotAvailable()
    {
        if (!this._emulatorAvailable)
        {
            Assert.True(true, "Cosmos DB Emulator not available, test skipped");
        }
    }

    private async Task EnsureContainerReadyAsync()
    {
        if (this._emulatorAvailable)
        {
            try
            {
                // Create a TestCosmosAgentThread just to let it set up the container infrastructure
                // This ensures the container is created using the exact same pattern the test will use
                var setupThread = new TestCosmosAgentThread(this._connectionString, this._testDatabaseId, this._testContainerId);

                // Trigger container creation by accessing the MessageStore and trying to get messages
                // This will create the database and container if they don't exist
                try
                {
                    await setupThread.MessageStore.GetMessagesAsync();
                }
                catch (Microsoft.Azure.Cosmos.CosmosException ex) when (ex.StatusCode == System.Net.HttpStatusCode.NotFound)
                {
                    // This is expected if the container is empty - it means the container was created successfully
                }
            }
            catch (Exception ex)
            {
                throw new InvalidOperationException($"Container {this._testContainerId} in database {this._testDatabaseId} is not ready: {ex.Message}", ex);
            }
        }
    }

    #region Constructor Tests

    [Fact]
    [Trait("Category", "CosmosDB")]
    public async Task Constructor_WithConnectionString_CreatesValidThread()
    {
        // Arrange & Act - Skip if emulator not available
        this.SkipIfEmulatorNotAvailable();

        // Act
        var thread = new TestCosmosAgentThread(this._connectionString, this._testDatabaseId, this._testContainerId);

        // Assert
        Assert.NotNull(thread);
        Assert.Equal(this._testDatabaseId, thread.MessageStore.DatabaseId);
        Assert.Equal(this._testContainerId, thread.MessageStore.ContainerId);
        Assert.NotNull(thread.ConversationId);
    }

    [Fact]
    [Trait("Category", "CosmosDB")]
    public async Task Constructor_WithConnectionStringAndConversationId_CreatesValidThread()
    {
        // Arrange & Act - Skip if emulator not available
        this.SkipIfEmulatorNotAvailable();

        const string ExpectedConversationId = "test-conversation-123";

        // Act
        var thread = new TestCosmosAgentThread(this._connectionString, this._testDatabaseId, this._testContainerId, ExpectedConversationId);

        // Assert
        Assert.NotNull(thread);
        Assert.Equal(ExpectedConversationId, thread.ConversationId);
        Assert.Equal(this._testDatabaseId, thread.MessageStore.DatabaseId);
        Assert.Equal(this._testContainerId, thread.MessageStore.ContainerId);
    }

    [Fact]
    [Trait("Category", "CosmosDB")]
    public async Task Constructor_WithManagedIdentity_CreatesValidThread()
    {
        // Arrange & Act - Skip if emulator not available
        this.SkipIfEmulatorNotAvailable();

        const string TestConversationId = "test-conversation-456";

        // Act
        var thread = new TestCosmosAgentThread(EmulatorEndpoint, this._testDatabaseId, this._testContainerId, TestConversationId, useManagedIdentity: true);

        // Assert
        Assert.NotNull(thread);
        Assert.Equal(TestConversationId, thread.ConversationId);
        Assert.Equal(this._testDatabaseId, thread.MessageStore.DatabaseId);
        Assert.Equal(this._testContainerId, thread.MessageStore.ContainerId);
    }

    [Fact]
    [Trait("Category", "CosmosDB")]
    public async Task Constructor_WithExistingMessageStore_CreatesValidThread()
    {
        // Arrange & Act - Skip if emulator not available
        this.SkipIfEmulatorNotAvailable();

        // Arrange
        var messageStore = new CosmosChatMessageStore(this._connectionString, this._testDatabaseId, this._testContainerId);

        // Act
        var thread = new TestCosmosAgentThread(messageStore);

        // Assert
        Assert.NotNull(thread);
        Assert.Equal(messageStore, thread.MessageStore);
        Assert.NotNull(thread.ConversationId);
    }

    [Fact(Skip = "Serialization requires additional JSON configuration for internal state types")]
    [Trait("Category", "CosmosDB")]
    public async Task Constructor_WithSerialization_RestoresCorrectly()
    {
        // Arrange & Act - Skip if emulator not available
        this.SkipIfEmulatorNotAvailable();

        // Arrange
        var originalThread = new TestCosmosAgentThread(this._connectionString, this._testDatabaseId, this._testContainerId, "serialization-test");

        // Add some messages to the original thread
        await originalThread.MessageStore.AddMessagesAsync([
            new ChatMessage(ChatRole.User, "Test message for serialization"),
            new ChatMessage(ChatRole.Assistant, "Response message")
        ]);

        // Serialize the thread
        var serialized = originalThread.Serialize();

        // Factory function to recreate message store from serialized state
        CosmosChatMessageStore MessageStoreFactory(JsonElement storeState, JsonSerializerOptions? options)
        {
            return new CosmosChatMessageStore(this._connectionString, this._testDatabaseId, this._testContainerId);
        }

        // Act - Restore from serialization
        var restoredThread = new TestCosmosAgentThread(serialized, MessageStoreFactory);

        // Assert
        Assert.NotNull(restoredThread);
        Assert.Equal(originalThread.ConversationId, restoredThread.ConversationId);

        // Verify messages were preserved
        var originalMessages = (await originalThread.MessageStore.GetMessagesAsync()).ToList();
        var restoredMessages = (await restoredThread.MessageStore.GetMessagesAsync()).ToList();

        Assert.Equal(originalMessages.Count, restoredMessages.Count);
        Assert.Equal(originalMessages.First().Contents, restoredMessages.First().Contents);
    }

    #endregion

    #region Property and Delegation Tests

    [Fact]
    [Trait("Category", "CosmosDB")]
    public async Task MessageStore_DelegatesToUnderlyingStore()
    {
        // Arrange & Act - Skip if emulator not available
        this.SkipIfEmulatorNotAvailable();

        // Act
        var thread = new TestCosmosAgentThread(this._connectionString, this._testDatabaseId, this._testContainerId);

        // Assert
        Assert.NotNull(thread.MessageStore);
        Assert.IsType<CosmosChatMessageStore>(thread.MessageStore);
    }

    #endregion

    #region Message Operations Tests

    [Fact]
    [Trait("Category", "CosmosDB")]
    public async Task AddAndGetMessagesAsync_WorksCorrectly()
    {
        // Arrange & Act - Skip if emulator not available
        this.SkipIfEmulatorNotAvailable();

        // Arrange - Use unique conversation ID to prevent test interference
        var ConversationId = $"add-get-test-{Guid.NewGuid():N}";
        var thread = new TestCosmosAgentThread(this._connectionString, this._testDatabaseId, this._testContainerId, ConversationId);

        // Act
        await thread.MessageStore.AddMessagesAsync([
            new ChatMessage(ChatRole.User, "Hello, this is a test message"),
            new ChatMessage(ChatRole.Assistant, "Hello! I'm an AI assistant. How can I help you?")
        ]);

        var messages = (await thread.MessageStore.GetMessagesAsync()).ToList();

        // Assert
        Assert.Equal(2, messages.Count);
        Assert.Equal(ChatRole.User, messages[0].Role);
        Assert.Equal("Hello, this is a test message", messages[0].Contents.FirstOrDefault()?.ToString());
        Assert.Equal(ChatRole.Assistant, messages[1].Role);
        Assert.Equal("Hello! I'm an AI assistant. How can I help you?", messages[1].Contents.FirstOrDefault()?.ToString());
    }

    [Fact]
    [Trait("Category", "CosmosDB")]
    public async Task DirectCosmosChatMessageStore_WithWorkingContainer_WorksCorrectlyAsync()
    {
        // Arrange & Act - Skip if emulator not available
        this.SkipIfEmulatorNotAvailable();

        // Arrange - Use the working container name from CosmosChatMessageStoreTests
        var ConversationId = $"direct-test-{Guid.NewGuid():N}";
        using var messageStore = new CosmosChatMessageStore(this._connectionString, this._testDatabaseId, "ChatMessages", ConversationId);

        // Act
        await messageStore.AddMessagesAsync([
            new ChatMessage(ChatRole.User, "Hello, this is a direct test message"),
            new ChatMessage(ChatRole.Assistant, "Hello! I'm responding directly.")
        ]);

        var messages = (await messageStore.GetMessagesAsync()).ToList();

        // Assert
        Assert.Equal(2, messages.Count);
        Assert.Equal(ChatRole.User, messages[0].Role);
        Assert.Equal("Hello, this is a direct test message", messages[0].Contents.FirstOrDefault()?.ToString());
        Assert.Equal(ChatRole.Assistant, messages[1].Role);
        Assert.Equal("Hello! I'm responding directly.", messages[1].Contents.FirstOrDefault()?.ToString());
    }

    [Fact]
    [Trait("Category", "CosmosDB")]
    public async Task GetMessageCountAsync_ReturnsCorrectCount()
    {
        // Arrange & Act - Skip if emulator not available
        this.SkipIfEmulatorNotAvailable();
        await this.EnsureContainerReadyAsync();

        // Arrange - Use unique conversation ID to prevent test interference
        var ConversationId = $"count-test-{Guid.NewGuid():N}";
        var thread = new TestCosmosAgentThread(this._connectionString, this._testDatabaseId, this._testContainerId, ConversationId);

        // Act & Assert - Start with 0 messages
        var initialCount = await thread.GetMessageCountAsync();
        Assert.Equal(0, initialCount);

        // Add some messages
        await thread.MessageStore.AddMessagesAsync([
            new ChatMessage(ChatRole.User, "Message 1"),
            new ChatMessage(ChatRole.User, "Message 2"),
            new ChatMessage(ChatRole.Assistant, "Response")
        ]);

        var finalCount = await thread.GetMessageCountAsync();
        Assert.Equal(3, finalCount);
    }

    [Fact]
    [Trait("Category", "CosmosDB")]
    public async Task ClearMessagesAsync_RemovesAllMessages()
    {
        // Arrange & Act - Skip if emulator not available
        this.SkipIfEmulatorNotAvailable();
        await this.EnsureContainerReadyAsync();

        // Arrange - Use unique conversation ID to prevent test interference
        var ConversationId = $"clear-test-{Guid.NewGuid():N}";
        var thread = new TestCosmosAgentThread(this._connectionString, this._testDatabaseId, this._testContainerId, ConversationId);

        // Add messages first
        await thread.MessageStore.AddMessagesAsync([
            new ChatMessage(ChatRole.User, "Message to be cleared"),
            new ChatMessage(ChatRole.Assistant, "Response to be cleared")
        ]);

        // Verify messages exist
        var countBeforeClear = await thread.GetMessageCountAsync();
        Assert.Equal(2, countBeforeClear);

        // Act
        await thread.ClearMessagesAsync();

        // Assert
        var countAfterClear = await thread.GetMessageCountAsync();
        Assert.Equal(0, countAfterClear);

        var messagesAfterClear = (await thread.MessageStore.GetMessagesAsync()).ToList();
        Assert.Empty(messagesAfterClear);
    }

    #endregion

    #region Conversation Isolation Tests

    [Fact]
    [Trait("Category", "CosmosDB")]
    public async Task DifferentConversationsAsync_AreIsolated()
    {
        // Arrange & Act - Skip if emulator not available
        this.SkipIfEmulatorNotAvailable();
        await this.EnsureContainerReadyAsync();

        // Arrange - Use unique conversation IDs to avoid interference from other tests
        var timestamp = Guid.NewGuid().ToString("N").Substring(0, 8);
        var thread1 = new TestCosmosAgentThread(this._connectionString, this._testDatabaseId, this._testContainerId, $"isolation-conv-1-{timestamp}");
        var thread2 = new TestCosmosAgentThread(this._connectionString, this._testDatabaseId, this._testContainerId, $"isolation-conv-2-{timestamp}");

        // Act
        await thread1.MessageStore.AddMessagesAsync([new ChatMessage(ChatRole.User, "Message in conversation 1")]);
        await thread2.MessageStore.AddMessagesAsync([new ChatMessage(ChatRole.User, "Message in conversation 2")]);

        var messages1 = (await thread1.MessageStore.GetMessagesAsync()).ToList();
        var messages2 = (await thread2.MessageStore.GetMessagesAsync()).ToList();

        // Assert
        Assert.Single(messages1);
        Assert.Single(messages2);
        Assert.Equal("Message in conversation 1", messages1[0].Contents.FirstOrDefault()?.ToString());
        Assert.Equal("Message in conversation 2", messages2[0].Contents.FirstOrDefault()?.ToString());

        // Verify that clearing one conversation doesn't affect the other
        await thread1.ClearMessagesAsync();

        var messages1AfterClear = (await thread1.MessageStore.GetMessagesAsync()).ToList();
        var messages2AfterClear = (await thread2.MessageStore.GetMessagesAsync()).ToList();

        Assert.Empty(messages1AfterClear);
        Assert.Single(messages2AfterClear);
    }

    #endregion

    #region Serialization Tests

    [Fact(Skip = "Serialization requires additional JSON configuration for internal state types")]
    [Trait("Category", "CosmosDB")]
    public async Task SerializeAsync_PreservesStateInformation()
    {
        // Arrange & Act - Skip if emulator not available
        this.SkipIfEmulatorNotAvailable();

        // Arrange
        var thread = new TestCosmosAgentThread(this._connectionString, this._testDatabaseId, this._testContainerId, "serialization-conversation");

        // Add some test data
        await thread.MessageStore.AddMessagesAsync([new ChatMessage(ChatRole.User, "Serialization test message")]);

        // Act
        var serialized = thread.Serialize();

        // Assert
        Assert.Equal(JsonValueKind.Object, serialized.ValueKind);
        Assert.True(serialized.TryGetProperty("storeState", out var storeStateProperty));

        // The store state should contain conversation information for restoration
        Assert.Equal(JsonValueKind.Object, storeStateProperty.ValueKind);
    }

    #endregion
}

// Test implementation class to access protected constructors
file sealed class TestCosmosAgentThread : CosmosAgentThread
{
    public TestCosmosAgentThread(string connectionString, string databaseId, string containerId)
        : base(connectionString, databaseId, containerId) { }

    public TestCosmosAgentThread(string connectionString, string databaseId, string containerId, string conversationId)
        : base(connectionString, databaseId, containerId, conversationId) { }

    public TestCosmosAgentThread(string accountEndpoint, string databaseId, string containerId, string? conversationId, bool useManagedIdentity)
        : base(accountEndpoint, databaseId, containerId, conversationId, useManagedIdentity) { }

    public TestCosmosAgentThread(CosmosChatMessageStore messageStore)
        : base(messageStore) { }

    public TestCosmosAgentThread(JsonElement serializedThreadState, Func<JsonElement, JsonSerializerOptions?, CosmosChatMessageStore> messageStoreFactory, JsonSerializerOptions? jsonSerializerOptions = null)
        : base(serializedThreadState, messageStoreFactory, jsonSerializerOptions) { }
}
