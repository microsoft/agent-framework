// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json;
using System.Text.Json.Serialization.Metadata;
using System.Threading.Tasks;
using Azure.Core;
using Azure.Identity;
using Microsoft.Azure.Cosmos;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.CosmosNoSql.UnitTests;

/// <summary>
/// Contains tests for <see cref="CosmosChatMessageStore"/>.
///
/// Test Modes:
/// - Default Mode: Cleans up all test data after each test run (deletes database)
/// - Preserve Mode: Keeps containers and data for inspection in Cosmos DB Emulator Data Explorer
///
/// To enable Preserve Mode, set environment variable: COSMOS_PRESERVE_CONTAINERS=true
/// Example: $env:COSMOS_PRESERVE_CONTAINERS="true"; dotnet test
///
/// In Preserve Mode, you can view the data in Cosmos DB Emulator Data Explorer at:
/// https://localhost:8081/_explorer/index.html
/// Database: AgentFrameworkTests
/// Container: ChatMessages
///
/// Environment Variable Reference:
/// | Variable | Values | Description |
/// |----------|--------|-------------|
/// | COSMOS_PRESERVE_CONTAINERS | true / false | Controls whether to preserve test data after completion |
///
/// Usage Examples:
/// - Run all tests in preserve mode: $env:COSMOS_PRESERVE_CONTAINERS="true"; dotnet test tests/Microsoft.Agents.AI.CosmosNoSql.UnitTests/
/// - Run specific test category in preserve mode: $env:COSMOS_PRESERVE_CONTAINERS="true"; dotnet test tests/Microsoft.Agents.AI.CosmosNoSql.UnitTests/ --filter "Category=CosmosDB"
/// - Reset to cleanup mode: $env:COSMOS_PRESERVE_CONTAINERS=""; dotnet test tests/Microsoft.Agents.AI.CosmosNoSql.UnitTests/
/// </summary>
[Collection("CosmosDB")]
public sealed class CosmosChatMessageStoreTests : IAsyncLifetime, IDisposable
{
    // Cosmos DB Emulator connection settings
    private const string EmulatorEndpoint = "https://localhost:8081";
    private const string EmulatorKey = "C2y6yDjf5/R+ob0N8A7Cgv30VRDJIWEHLM+4QDU5DE2nQ9nDuVTqobD4b8mGGyPMbIZnqyMsEcaGQy67XIw/Jw==";
    private const string TestContainerId = "ChatMessages";
    private const string HierarchicalTestContainerId = "HierarchicalChatMessages";
    // Use unique database ID per test class instance to avoid conflicts  
#pragma warning disable CA1802 // Use literals where appropriate
    private static readonly string s_testDatabaseId = $"AgentFrameworkTests-ChatStore-{Guid.NewGuid():N}";
#pragma warning restore CA1802

    private string _connectionString = string.Empty;
    private bool _emulatorAvailable;
    private bool _preserveContainer;
    private CosmosClient? _setupClient; // Only used for test setup/cleanup

    public async Task InitializeAsync()
    {
        // Fail fast if emulator is not available
        this.SkipIfEmulatorNotAvailable();

        // Check environment variable to determine if we should preserve containers
        // Set COSMOS_PRESERVE_CONTAINERS=true to keep containers and data for inspection
        this._preserveContainer = string.Equals(Environment.GetEnvironmentVariable("COSMOS_PRESERVE_CONTAINERS"), "true", StringComparison.OrdinalIgnoreCase);

        this._connectionString = $"AccountEndpoint={EmulatorEndpoint};AccountKey={EmulatorKey}";

        try
        {
            // Only create CosmosClient for test setup - the actual tests will use connection string constructors
            this._setupClient = new CosmosClient(EmulatorEndpoint, EmulatorKey);

            // Test connection by attempting to create database
            var databaseResponse = await this._setupClient.CreateDatabaseIfNotExistsAsync(s_testDatabaseId);

            // Create container for simple partitioning tests
            await databaseResponse.Database.CreateContainerIfNotExistsAsync(
                TestContainerId,
                "/conversationId",
                throughput: 400);

            // Create container for hierarchical partitioning tests with hierarchical partition key
            var hierarchicalContainerProperties = new ContainerProperties(HierarchicalTestContainerId, ["/tenantId", "/userId", "/sessionId"]);
            await databaseResponse.Database.CreateContainerIfNotExistsAsync(
                hierarchicalContainerProperties,
                throughput: 400);

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
                if (this._preserveContainer)
                {
                    // Preserve mode: Don't delete the database/container, keep data for inspection
                    // This allows viewing data in the Cosmos DB Emulator Data Explorer
                    // No cleanup needed - data persists for debugging
                }
                else
                {
                    // Clean mode: Delete the test database and all data
                    var database = this._setupClient.GetDatabase(s_testDatabaseId);
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

    public void Dispose()
    {
        this._setupClient?.Dispose();
        GC.SuppressFinalize(this);
    }

    private void SkipIfEmulatorNotAvailable()
    {
        // In CI: Skip if COSMOS_EMULATOR_AVAILABLE is not set to "true"
        // Locally: Skip if emulator connection check failed
        var ciEmulatorAvailable = string.Equals(Environment.GetEnvironmentVariable("COSMOS_EMULATOR_AVAILABLE"), "true", StringComparison.OrdinalIgnoreCase);

        Xunit.Skip.If(!ciEmulatorAvailable && !this._emulatorAvailable, "Cosmos DB Emulator is not available");
    }

    #region Constructor Tests

    [SkippableFact]
    [Trait("Category", "CosmosDB")]
    public void Constructor_WithConnectionString_ShouldCreateInstance()
    {
        // Arrange & Act
        this.SkipIfEmulatorNotAvailable();

        // Act
        using var store = new CosmosChatMessageStore(this._connectionString, s_testDatabaseId, TestContainerId, "test-conversation");

        // Assert
        Assert.NotNull(store);
        Assert.Equal("test-conversation", store.ConversationId);
        Assert.Equal(s_testDatabaseId, store.DatabaseId);
        Assert.Equal(TestContainerId, store.ContainerId);
    }

    [SkippableFact]
    [Trait("Category", "CosmosDB")]
    public void Constructor_WithConnectionStringNoConversationId_ShouldCreateInstance()
    {
        // Arrange
        this.SkipIfEmulatorNotAvailable();

        // Act
        using var store = new CosmosChatMessageStore(this._connectionString, s_testDatabaseId, TestContainerId);

        // Assert
        Assert.NotNull(store);
        Assert.NotNull(store.ConversationId);
        Assert.Equal(s_testDatabaseId, store.DatabaseId);
        Assert.Equal(TestContainerId, store.ContainerId);
    }

    [SkippableFact]
    [Trait("Category", "CosmosDB")]
    public void Constructor_WithNullConnectionString_ShouldThrowArgumentException()
    {
        // Arrange & Act & Assert
        Assert.Throws<ArgumentNullException>(() =>
            new CosmosChatMessageStore((string)null!, s_testDatabaseId, TestContainerId, "test-conversation"));
    }

    [SkippableFact]
    [Trait("Category", "CosmosDB")]
    public void Constructor_WithEmptyConversationId_ShouldThrowArgumentException()
    {
        // Arrange & Act & Assert
        this.SkipIfEmulatorNotAvailable();

        Assert.Throws<ArgumentException>(() =>
            new CosmosChatMessageStore(this._connectionString, s_testDatabaseId, TestContainerId, ""));
    }

    #endregion

    #region InvokedAsync Tests

    [SkippableFact]
    [Trait("Category", "CosmosDB")]
    public async Task InvokedAsync_WithSingleMessage_ShouldAddMessageAsync()
    {
        // Arrange
        this.SkipIfEmulatorNotAvailable();
        var conversationId = Guid.NewGuid().ToString();
        using var store = new CosmosChatMessageStore(this._connectionString, s_testDatabaseId, TestContainerId, conversationId);
        var message = new ChatMessage(ChatRole.User, "Hello, world!");

        var context = new ChatMessageStore.InvokedContext([message], [])
        {
            ResponseMessages = []
        };

        // Act
        await store.InvokedAsync(context);

        // Wait a moment for eventual consistency
        await Task.Delay(100);

        // Assert
        var invokingContext = new ChatMessageStore.InvokingContext([]);
        var messages = await store.InvokingAsync(invokingContext);
        var messageList = messages.ToList();

        // Simple assertion - if this fails, we know the deserialization is the issue
        if (messageList.Count == 0)
        {
            // Let's check if we can find ANY items in the container for this conversation
            var directQuery = new QueryDefinition("SELECT VALUE COUNT(1) FROM c WHERE c.conversationId = @conversationId")
                .WithParameter("@conversationId", conversationId);
            var countIterator = this._setupClient!.GetDatabase(s_testDatabaseId).GetContainer(TestContainerId)
                .GetItemQueryIterator<int>(directQuery, requestOptions: new QueryRequestOptions
                {
                    PartitionKey = new PartitionKey(conversationId)
                });

            var countResponse = await countIterator.ReadNextAsync();
            var count = countResponse.FirstOrDefault();

            // Debug: Let's see what the raw query returns
            var rawQuery = new QueryDefinition("SELECT * FROM c WHERE c.conversationId = @conversationId")
                .WithParameter("@conversationId", conversationId);
            var rawIterator = this._setupClient!.GetDatabase(s_testDatabaseId).GetContainer(TestContainerId)
                .GetItemQueryIterator<dynamic>(rawQuery, requestOptions: new QueryRequestOptions
                {
                    PartitionKey = new PartitionKey(conversationId)
                });

            List<dynamic> rawResults = [];
            while (rawIterator.HasMoreResults)
            {
                var rawResponse = await rawIterator.ReadNextAsync();
                rawResults.AddRange(rawResponse);
            }

            string rawJson = rawResults.Count > 0 ? Newtonsoft.Json.JsonConvert.SerializeObject(rawResults[0], Newtonsoft.Json.Formatting.Indented) : "null";
            Assert.Fail($"InvokingAsync returned 0 messages, but direct count query found {count} items for conversation {conversationId}. Raw document: {rawJson}");
        }

        Assert.Single(messageList);
        Assert.Equal("Hello, world!", messageList[0].Text);
        Assert.Equal(ChatRole.User, messageList[0].Role);
    }

    [SkippableFact]
    [Trait("Category", "CosmosDB")]
    public async Task InvokedAsync_WithMultipleMessages_ShouldAddAllMessagesAsync()
    {
        // Arrange
        this.SkipIfEmulatorNotAvailable();
        var conversationId = Guid.NewGuid().ToString();
        using var store = new CosmosChatMessageStore(this._connectionString, s_testDatabaseId, TestContainerId, conversationId);
        var requestMessages = new[]
        {
            new ChatMessage(ChatRole.User, "First message"),
            new ChatMessage(ChatRole.Assistant, "Second message"),
            new ChatMessage(ChatRole.User, "Third message")
        };
        var aiContextProviderMessages = new[]
        {
            new ChatMessage(ChatRole.System, "System context message")
        };
        var responseMessages = new[]
        {
            new ChatMessage(ChatRole.Assistant, "Response message")
        };

        var context = new ChatMessageStore.InvokedContext(requestMessages, [])
        {
            AIContextProviderMessages = aiContextProviderMessages,
            ResponseMessages = responseMessages
        };

        // Act
        await store.InvokedAsync(context);

        // Assert
        var invokingContext = new ChatMessageStore.InvokingContext([]);
        var retrievedMessages = await store.InvokingAsync(invokingContext);
        var messageList = retrievedMessages.ToList();
        Assert.Equal(5, messageList.Count);
        Assert.Equal("First message", messageList[0].Text);
        Assert.Equal("Second message", messageList[1].Text);
        Assert.Equal("Third message", messageList[2].Text);
        Assert.Equal("System context message", messageList[3].Text);
        Assert.Equal("Response message", messageList[4].Text);
    }

    #endregion

    #region InvokingAsync Tests

    [SkippableFact]
    [Trait("Category", "CosmosDB")]
    public async Task InvokingAsync_WithNoMessages_ShouldReturnEmptyAsync()
    {
        // Arrange
        this.SkipIfEmulatorNotAvailable();
        using var store = new CosmosChatMessageStore(this._connectionString, s_testDatabaseId, TestContainerId, Guid.NewGuid().ToString());

        // Act
        var invokingContext = new ChatMessageStore.InvokingContext([]);
        var messages = await store.InvokingAsync(invokingContext);

        // Assert
        Assert.Empty(messages);
    }

    [SkippableFact]
    [Trait("Category", "CosmosDB")]
    public async Task InvokingAsync_WithConversationIsolation_ShouldOnlyReturnMessagesForConversationAsync()
    {
        // Arrange
        this.SkipIfEmulatorNotAvailable();
        var conversation1 = Guid.NewGuid().ToString();
        var conversation2 = Guid.NewGuid().ToString();

        using var store1 = new CosmosChatMessageStore(this._connectionString, s_testDatabaseId, TestContainerId, conversation1);
        using var store2 = new CosmosChatMessageStore(this._connectionString, s_testDatabaseId, TestContainerId, conversation2);

        var context1 = new ChatMessageStore.InvokedContext([new ChatMessage(ChatRole.User, "Message for conversation 1")], []);
        var context2 = new ChatMessageStore.InvokedContext([new ChatMessage(ChatRole.User, "Message for conversation 2")], []);

        await store1.InvokedAsync(context1);
        await store2.InvokedAsync(context2);

        // Act
        var invokingContext1 = new ChatMessageStore.InvokingContext([]);
        var invokingContext2 = new ChatMessageStore.InvokingContext([]);

        var messages1 = await store1.InvokingAsync(invokingContext1);
        var messages2 = await store2.InvokingAsync(invokingContext2);

        // Assert
        var messageList1 = messages1.ToList();
        var messageList2 = messages2.ToList();
        Assert.Single(messageList1);
        Assert.Single(messageList2);
        Assert.Equal("Message for conversation 1", messageList1[0].Text);
        Assert.Equal("Message for conversation 2", messageList2[0].Text);
    }

    #endregion

    #region Integration Tests

    [SkippableFact]
    [Trait("Category", "CosmosDB")]
    public async Task FullWorkflow_AddAndGet_ShouldWorkCorrectlyAsync()
    {
        // Arrange
        this.SkipIfEmulatorNotAvailable();
        var conversationId = $"test-conversation-{Guid.NewGuid():N}"; // Use unique conversation ID
        using var originalStore = new CosmosChatMessageStore(this._connectionString, s_testDatabaseId, TestContainerId, conversationId);

        var messages = new[]
        {
            new ChatMessage(ChatRole.System, "You are a helpful assistant."),
            new ChatMessage(ChatRole.User, "Hello!"),
            new ChatMessage(ChatRole.Assistant, "Hi there! How can I help you today?"),
            new ChatMessage(ChatRole.User, "What's the weather like?"),
            new ChatMessage(ChatRole.Assistant, "I'm sorry, I don't have access to current weather data.")
        };

        // Act 1: Add messages
        var invokedContext = new ChatMessageStore.InvokedContext(messages, []);
        await originalStore.InvokedAsync(invokedContext);

        // Act 2: Verify messages were added
        var invokingContext = new ChatMessageStore.InvokingContext([]);
        var retrievedMessages = await originalStore.InvokingAsync(invokingContext);
        var retrievedList = retrievedMessages.ToList();
        Assert.Equal(5, retrievedList.Count);

        // Act 3: Create new store instance for same conversation (test persistence)
        using var newStore = new CosmosChatMessageStore(this._connectionString, s_testDatabaseId, TestContainerId, conversationId);
        var persistedMessages = await newStore.InvokingAsync(invokingContext);
        var persistedList = persistedMessages.ToList();

        // Assert final state
        Assert.Equal(5, persistedList.Count);
        Assert.Equal("You are a helpful assistant.", persistedList[0].Text);
        Assert.Equal("Hello!", persistedList[1].Text);
        Assert.Equal("Hi there! How can I help you today?", persistedList[2].Text);
        Assert.Equal("What's the weather like?", persistedList[3].Text);
        Assert.Equal("I'm sorry, I don't have access to current weather data.", persistedList[4].Text);
    }

    #endregion

    #region Disposal Tests

    [SkippableFact]
    [Trait("Category", "CosmosDB")]
    public void Dispose_AfterUse_ShouldNotThrow()
    {
        // Arrange
        this.SkipIfEmulatorNotAvailable();
        var store = new CosmosChatMessageStore(this._connectionString, s_testDatabaseId, TestContainerId, Guid.NewGuid().ToString());

        // Act & Assert
        store.Dispose(); // Should not throw
    }

    [SkippableFact]
    [Trait("Category", "CosmosDB")]
    public void Dispose_MultipleCalls_ShouldNotThrow()
    {
        // Arrange
        this.SkipIfEmulatorNotAvailable();
        var store = new CosmosChatMessageStore(this._connectionString, s_testDatabaseId, TestContainerId, Guid.NewGuid().ToString());

        // Act & Assert
        store.Dispose(); // First call
        store.Dispose(); // Second call - should not throw
    }

    #endregion

    #region Hierarchical Partitioning Tests

    [SkippableFact]
    [Trait("Category", "CosmosDB")]
    public void Constructor_WithHierarchicalConnectionString_ShouldCreateInstance()
    {
        // Arrange & Act
        this.SkipIfEmulatorNotAvailable();

        // Act
        using var store = new CosmosChatMessageStore(this._connectionString, s_testDatabaseId, HierarchicalTestContainerId, "tenant-123", "user-456", "session-789");

        // Assert
        Assert.NotNull(store);
        Assert.Equal("session-789", store.ConversationId);
        Assert.Equal(s_testDatabaseId, store.DatabaseId);
        Assert.Equal(HierarchicalTestContainerId, store.ContainerId);
    }

    [SkippableFact]
    [Trait("Category", "CosmosDB")]
    public void Constructor_WithHierarchicalEndpoint_ShouldCreateInstance()
    {
        // Arrange & Act
        this.SkipIfEmulatorNotAvailable();

        // Act
        TokenCredential credential = new DefaultAzureCredential();
        using var store = new CosmosChatMessageStore(EmulatorEndpoint, credential, s_testDatabaseId, HierarchicalTestContainerId, "tenant-123", "user-456", "session-789");

        // Assert
        Assert.NotNull(store);
        Assert.Equal("session-789", store.ConversationId);
        Assert.Equal(s_testDatabaseId, store.DatabaseId);
        Assert.Equal(HierarchicalTestContainerId, store.ContainerId);
    }

    [SkippableFact]
    [Trait("Category", "CosmosDB")]
    public void Constructor_WithHierarchicalCosmosClient_ShouldCreateInstance()
    {
        // Arrange & Act
        this.SkipIfEmulatorNotAvailable();

        using var cosmosClient = new CosmosClient(EmulatorEndpoint, EmulatorKey);
        using var store = new CosmosChatMessageStore(cosmosClient, s_testDatabaseId, HierarchicalTestContainerId, "tenant-123", "user-456", "session-789");

        // Assert
        Assert.NotNull(store);
        Assert.Equal("session-789", store.ConversationId);
        Assert.Equal(s_testDatabaseId, store.DatabaseId);
        Assert.Equal(HierarchicalTestContainerId, store.ContainerId);
    }

    [SkippableFact]
    [Trait("Category", "CosmosDB")]
    public void Constructor_WithHierarchicalNullTenantId_ShouldThrowArgumentException()
    {
        // Arrange & Act & Assert
        this.SkipIfEmulatorNotAvailable();

        Assert.Throws<ArgumentNullException>(() =>
            new CosmosChatMessageStore(this._connectionString, s_testDatabaseId, TestContainerId, null!, "user-456", "session-789"));
    }

    [SkippableFact]
    [Trait("Category", "CosmosDB")]
    public void Constructor_WithHierarchicalEmptyUserId_ShouldThrowArgumentException()
    {
        // Arrange & Act & Assert
        this.SkipIfEmulatorNotAvailable();

        Assert.Throws<ArgumentException>(() =>
            new CosmosChatMessageStore(this._connectionString, s_testDatabaseId, HierarchicalTestContainerId, "tenant-123", "", "session-789"));
    }

    [SkippableFact]
    [Trait("Category", "CosmosDB")]
    public void Constructor_WithHierarchicalWhitespaceSessionId_ShouldThrowArgumentException()
    {
        // Arrange & Act & Assert
        this.SkipIfEmulatorNotAvailable();

        Assert.Throws<ArgumentException>(() =>
            new CosmosChatMessageStore(this._connectionString, s_testDatabaseId, HierarchicalTestContainerId, "tenant-123", "user-456", "   "));
    }

    [SkippableFact]
    [Trait("Category", "CosmosDB")]
    public async Task InvokedAsync_WithHierarchicalPartitioning_ShouldAddMessageWithMetadataAsync()
    {
        // Arrange
        this.SkipIfEmulatorNotAvailable();
        const string TenantId = "tenant-123";
        const string UserId = "user-456";
        const string SessionId = "session-789";
        // Test hierarchical partitioning constructor with connection string
        using var store = new CosmosChatMessageStore(this._connectionString, s_testDatabaseId, HierarchicalTestContainerId, TenantId, UserId, SessionId);
        var message = new ChatMessage(ChatRole.User, "Hello from hierarchical partitioning!");

        var context = new ChatMessageStore.InvokedContext([message], []);

        // Act
        await store.InvokedAsync(context);

        // Wait a moment for eventual consistency
        await Task.Delay(100);

        // Assert
        var invokingContext = new ChatMessageStore.InvokingContext([]);
        var messages = await store.InvokingAsync(invokingContext);
        var messageList = messages.ToList();

        Assert.Single(messageList);
        Assert.Equal("Hello from hierarchical partitioning!", messageList[0].Text);
        Assert.Equal(ChatRole.User, messageList[0].Role);

        // Verify that the document is stored with hierarchical partitioning metadata
        var directQuery = new QueryDefinition("SELECT * FROM c WHERE c.conversationId = @conversationId AND c.type = @type")
            .WithParameter("@conversationId", SessionId)
            .WithParameter("@type", "ChatMessage");

        var iterator = this._setupClient!.GetDatabase(s_testDatabaseId).GetContainer(HierarchicalTestContainerId)
            .GetItemQueryIterator<dynamic>(directQuery, requestOptions: new QueryRequestOptions
            {
                PartitionKey = new PartitionKeyBuilder().Add(TenantId).Add(UserId).Add(SessionId).Build()
            });

        var response = await iterator.ReadNextAsync();
        var document = response.FirstOrDefault();

        Assert.NotNull(document);
        // The document should have hierarchical metadata
        Assert.Equal(SessionId, (string)document!.conversationId);
        Assert.Equal(TenantId, (string)document!.tenantId);
        Assert.Equal(UserId, (string)document!.userId);
        Assert.Equal(SessionId, (string)document!.sessionId);
    }

    [SkippableFact]
    [Trait("Category", "CosmosDB")]
    public async Task InvokedAsync_WithHierarchicalMultipleMessages_ShouldAddAllMessagesAsync()
    {
        // Arrange
        this.SkipIfEmulatorNotAvailable();
        const string TenantId = "tenant-batch";
        const string UserId = "user-batch";
        const string SessionId = "session-batch";
        // Test hierarchical partitioning constructor with connection string
        using var store = new CosmosChatMessageStore(this._connectionString, s_testDatabaseId, HierarchicalTestContainerId, TenantId, UserId, SessionId);
        var messages = new[]
        {
            new ChatMessage(ChatRole.User, "First hierarchical message"),
            new ChatMessage(ChatRole.Assistant, "Second hierarchical message"),
            new ChatMessage(ChatRole.User, "Third hierarchical message")
        };

        var context = new ChatMessageStore.InvokedContext(messages, []);

        // Act
        await store.InvokedAsync(context);

        // Wait a moment for eventual consistency
        await Task.Delay(100);

        // Assert
        var invokingContext = new ChatMessageStore.InvokingContext([]);
        var retrievedMessages = await store.InvokingAsync(invokingContext);
        var messageList = retrievedMessages.ToList();

        Assert.Equal(3, messageList.Count);
        Assert.Equal("First hierarchical message", messageList[0].Text);
        Assert.Equal("Second hierarchical message", messageList[1].Text);
        Assert.Equal("Third hierarchical message", messageList[2].Text);
    }

    [SkippableFact]
    [Trait("Category", "CosmosDB")]
    public async Task InvokingAsync_WithHierarchicalPartitionIsolation_ShouldIsolateMessagesByUserIdAsync()
    {
        // Arrange
        this.SkipIfEmulatorNotAvailable();
        const string TenantId = "tenant-isolation";
        const string UserId1 = "user-1";
        const string UserId2 = "user-2";
        const string SessionId = "session-isolation";

        // Different userIds create different hierarchical partitions, providing proper isolation
        using var store1 = new CosmosChatMessageStore(this._connectionString, s_testDatabaseId, HierarchicalTestContainerId, TenantId, UserId1, SessionId);
        using var store2 = new CosmosChatMessageStore(this._connectionString, s_testDatabaseId, HierarchicalTestContainerId, TenantId, UserId2, SessionId);

        // Add messages to both stores
        var context1 = new ChatMessageStore.InvokedContext([new ChatMessage(ChatRole.User, "Message from user 1")], []);
        var context2 = new ChatMessageStore.InvokedContext([new ChatMessage(ChatRole.User, "Message from user 2")], []);

        await store1.InvokedAsync(context1);
        await store2.InvokedAsync(context2);

        // Wait a moment for eventual consistency
        await Task.Delay(100);

        // Act & Assert
        var invokingContext1 = new ChatMessageStore.InvokingContext([]);
        var invokingContext2 = new ChatMessageStore.InvokingContext([]);

        var messages1 = await store1.InvokingAsync(invokingContext1);
        var messageList1 = messages1.ToList();

        var messages2 = await store2.InvokingAsync(invokingContext2);
        var messageList2 = messages2.ToList();

        // With true hierarchical partitioning, each user sees only their own messages
        Assert.Single(messageList1);
        Assert.Single(messageList2);
        Assert.Equal("Message from user 1", messageList1[0].Text);
        Assert.Equal("Message from user 2", messageList2[0].Text);
    }

    [SkippableFact]
    [Trait("Category", "CosmosDB")]
    public async Task SerializeDeserialize_WithHierarchicalPartitioning_ShouldPreserveStateAsync()
    {
        // Arrange
        this.SkipIfEmulatorNotAvailable();
        const string TenantId = "tenant-serialize";
        const string UserId = "user-serialize";
        const string SessionId = "session-serialize";

        using var originalStore = new CosmosChatMessageStore(this._connectionString, s_testDatabaseId, HierarchicalTestContainerId, TenantId, UserId, SessionId);

        var context = new ChatMessageStore.InvokedContext([new ChatMessage(ChatRole.User, "Test serialization message")], []);
        await originalStore.InvokedAsync(context);

        // Act - Serialize the store state
        var serializedState = originalStore.Serialize();

        // Create a new store from the serialized state
        using var cosmosClient = new CosmosClient(EmulatorEndpoint, EmulatorKey);
        var serializerOptions = new JsonSerializerOptions
        {
            TypeInfoResolver = new DefaultJsonTypeInfoResolver()
        };
        using var deserializedStore = CosmosChatMessageStore.CreateFromSerializedState(cosmosClient, serializedState, s_testDatabaseId, HierarchicalTestContainerId, serializerOptions);

        // Wait a moment for eventual consistency
        await Task.Delay(100);

        // Assert - The deserialized store should have the same functionality
        var invokingContext = new ChatMessageStore.InvokingContext([]);
        var messages = await deserializedStore.InvokingAsync(invokingContext);
        var messageList = messages.ToList();

        Assert.Single(messageList);
        Assert.Equal("Test serialization message", messageList[0].Text);
        Assert.Equal(SessionId, deserializedStore.ConversationId);
        Assert.Equal(s_testDatabaseId, deserializedStore.DatabaseId);
        Assert.Equal(HierarchicalTestContainerId, deserializedStore.ContainerId);
    }

    [SkippableFact]
    [Trait("Category", "CosmosDB")]
    public async Task HierarchicalAndSimplePartitioning_ShouldCoexistAsync()
    {
        // Arrange
        this.SkipIfEmulatorNotAvailable();
        const string SessionId = "coexist-session";

        // Create simple store using simple partitioning container and hierarchical store using hierarchical container
        using var simpleStore = new CosmosChatMessageStore(this._connectionString, s_testDatabaseId, TestContainerId, SessionId);
        using var hierarchicalStore = new CosmosChatMessageStore(this._connectionString, s_testDatabaseId, HierarchicalTestContainerId, "tenant-coexist", "user-coexist", SessionId);

        // Add messages to both
        var simpleContext = new ChatMessageStore.InvokedContext([new ChatMessage(ChatRole.User, "Simple partitioning message")], []);
        var hierarchicalContext = new ChatMessageStore.InvokedContext([new ChatMessage(ChatRole.User, "Hierarchical partitioning message")], []);

        await simpleStore.InvokedAsync(simpleContext);
        await hierarchicalStore.InvokedAsync(hierarchicalContext);

        // Wait a moment for eventual consistency
        await Task.Delay(100);

        // Act & Assert
        var invokingContext = new ChatMessageStore.InvokingContext([]);

        var simpleMessages = await simpleStore.InvokingAsync(invokingContext);
        var simpleMessageList = simpleMessages.ToList();

        var hierarchicalMessages = await hierarchicalStore.InvokingAsync(invokingContext);
        var hierarchicalMessageList = hierarchicalMessages.ToList();

        // Each should only see its own messages since they use different containers
        Assert.Single(simpleMessageList);
        Assert.Single(hierarchicalMessageList);
        Assert.Equal("Simple partitioning message", simpleMessageList[0].Text);
        Assert.Equal("Hierarchical partitioning message", hierarchicalMessageList[0].Text);
    }

    [SkippableFact]
    [Trait("Category", "CosmosDB")]
    public async Task MaxMessagesToRetrieve_ShouldLimitAndReturnMostRecentAsync()
    {
        // Arrange
        this.SkipIfEmulatorNotAvailable();
        const string ConversationId = "max-messages-test";

        using var store = new CosmosChatMessageStore(this._connectionString, s_testDatabaseId, TestContainerId, ConversationId);

        // Add 10 messages
        var messages = new List<ChatMessage>();
        for (int i = 1; i <= 10; i++)
        {
            messages.Add(new ChatMessage(ChatRole.User, $"Message {i}"));
            await Task.Delay(10); // Small delay to ensure different timestamps
        }

        var context = new ChatMessageStore.InvokedContext(messages, []);
        await store.InvokedAsync(context);

        // Wait for eventual consistency
        await Task.Delay(100);

        // Act - Set max to 5 and retrieve
        store.MaxMessagesToRetrieve = 5;
        var invokingContext = new ChatMessageStore.InvokingContext([]);
        var retrievedMessages = await store.InvokingAsync(invokingContext);
        var messageList = retrievedMessages.ToList();

        // Assert - Should get the 5 most recent messages (6-10) in ascending order
        Assert.Equal(5, messageList.Count);
        Assert.Equal("Message 6", messageList[0].Text);
        Assert.Equal("Message 7", messageList[1].Text);
        Assert.Equal("Message 8", messageList[2].Text);
        Assert.Equal("Message 9", messageList[3].Text);
        Assert.Equal("Message 10", messageList[4].Text);
    }

    [SkippableFact]
    [Trait("Category", "CosmosDB")]
    public async Task MaxMessagesToRetrieve_Null_ShouldReturnAllMessagesAsync()
    {
        // Arrange
        this.SkipIfEmulatorNotAvailable();
        const string ConversationId = "max-messages-null-test";

        using var store = new CosmosChatMessageStore(this._connectionString, s_testDatabaseId, TestContainerId, ConversationId);

        // Add 10 messages
        var messages = new List<ChatMessage>();
        for (int i = 1; i <= 10; i++)
        {
            messages.Add(new ChatMessage(ChatRole.User, $"Message {i}"));
        }

        var context = new ChatMessageStore.InvokedContext(messages, []);
        await store.InvokedAsync(context);

        // Wait for eventual consistency
        await Task.Delay(100);

        // Act - No limit set (default null)
        var invokingContext = new ChatMessageStore.InvokingContext([]);
        var retrievedMessages = await store.InvokingAsync(invokingContext);
        var messageList = retrievedMessages.ToList();

        // Assert - Should get all 10 messages
        Assert.Equal(10, messageList.Count);
        Assert.Equal("Message 1", messageList[0].Text);
        Assert.Equal("Message 10", messageList[9].Text);
    }

    #endregion
}
