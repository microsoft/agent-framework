// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading.Tasks;
using Microsoft.Azure.Cosmos;
using Microsoft.Extensions.AI;
using Microsoft.Agents.AI;
using Xunit;

namespace Microsoft.Agents.AI.Abstractions.UnitTests;

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
/// - Run all tests in preserve mode: $env:COSMOS_PRESERVE_CONTAINERS="true"; dotnet test tests/Microsoft.Agents.AI.Abstractions.UnitTests/
/// - Run specific test category in preserve mode: $env:COSMOS_PRESERVE_CONTAINERS="true"; dotnet test tests/Microsoft.Agents.AI.Abstractions.UnitTests/ --filter "Category=CosmosDB"
/// - Reset to cleanup mode: $env:COSMOS_PRESERVE_CONTAINERS=""; dotnet test tests/Microsoft.Agents.AI.Abstractions.UnitTests/
/// </summary>
[Collection("CosmosDB")]
public sealed class CosmosChatMessageStoreTests : IAsyncLifetime, IDisposable
{
    // Cosmos DB Emulator connection settings
    private const string EmulatorEndpoint = "https://localhost:8081";
    private const string EmulatorKey = "C2y6yDjf5/R+ob0N8A7Cgv30VRDJIWEHLM+4QDU5DE2nQ9nDuVTqobD4b8mGGyPMbIZnqyMsEcaGQy67XIw/Jw==";
    private const string TestDatabaseId = "AgentFrameworkTests";
    private const string TestContainerId = "ChatMessages";

    private string _connectionString = string.Empty;
    private bool _emulatorAvailable;
    private bool _preserveContainer;
    private CosmosClient? _setupClient; // Only used for test setup/cleanup

    public async Task InitializeAsync()
    {
        // Check environment variable to determine if we should preserve containers
        // Set COSMOS_PRESERVE_CONTAINERS=true to keep containers and data for inspection
        _preserveContainer = string.Equals(Environment.GetEnvironmentVariable("COSMOS_PRESERVE_CONTAINERS"), "true", StringComparison.OrdinalIgnoreCase);

        _connectionString = $"AccountEndpoint={EmulatorEndpoint};AccountKey={EmulatorKey}";

        try
        {
            // Only create CosmosClient for test setup - the actual tests will use connection string constructors
            _setupClient = new CosmosClient(EmulatorEndpoint, EmulatorKey);

            // Test connection by attempting to create database
            var databaseResponse = await this._setupClient.CreateDatabaseIfNotExistsAsync(TestDatabaseId);
            await databaseResponse.Database.CreateContainerIfNotExistsAsync(
                TestContainerId,
                "/conversationId",
                throughput: 400);

            _emulatorAvailable = true;
        }
        catch (Exception)
        {
            // Emulator not available, tests will be skipped
            _emulatorAvailable = false;
            _setupClient?.Dispose();
            _setupClient = null;
        }
    }

    public async Task DisposeAsync()
    {
        if (_setupClient != null && _emulatorAvailable)
        {
            try
            {
                if (_preserveContainer)
                {
                    // Preserve mode: Don't delete the database/container, keep data for inspection
                    // This allows viewing data in the Cosmos DB Emulator Data Explorer
                    // No cleanup needed - data persists for debugging
                }
                else
                {
                    // Clean mode: Delete the test database and all data
                    var database = _setupClient.GetDatabase(TestDatabaseId);
                    await database.DeleteAsync();
                }
            }
            catch
            {
                // Ignore cleanup errors
            }
            finally
            {
                _setupClient.Dispose();
            }
        }
    }

    public void Dispose()
    {
        _setupClient?.Dispose();
        GC.SuppressFinalize(this);
    }

    private void SkipIfEmulatorNotAvailable()
    {
        if (!_emulatorAvailable)
        {
            Assert.Fail("Cosmos DB Emulator is not available. Start the emulator to run these tests.");
        }
    }

    #region Constructor Tests

    [Fact]
    [Trait("Category", "CosmosDB")]
    public void Constructor_WithConnectionString_ShouldCreateInstance()
    {
        // Arrange & Act
        this.SkipIfEmulatorNotAvailable();

        // Act
        using var store = new CosmosChatMessageStore(this._connectionString, TestDatabaseId, TestContainerId, "test-conversation");

        // Assert
        Assert.NotNull(store);
        Assert.Equal("test-conversation", store.ConversationId);
        Assert.Equal(TestDatabaseId, store.DatabaseId);
        Assert.Equal(TestContainerId, store.ContainerId);
    }

    [Fact]
    [Trait("Category", "CosmosDB")]
    public void Constructor_WithConnectionStringNoConversationId_ShouldCreateInstance()
    {
        // Arrange
        this.SkipIfEmulatorNotAvailable();

        // Act
        using var store = new CosmosChatMessageStore(this._connectionString, TestDatabaseId, TestContainerId);

        // Assert
        Assert.NotNull(store);
        Assert.NotNull(store.ConversationId);
        Assert.Equal(TestDatabaseId, store.DatabaseId);
        Assert.Equal(TestContainerId, store.ContainerId);
    }

    [Fact]
    [Trait("Category", "CosmosDB")]
    public void Constructor_WithNullConnectionString_ShouldThrowArgumentException()
    {
        // Arrange & Act & Assert
        Assert.Throws<ArgumentException>(() =>
            new CosmosChatMessageStore((string)null!, TestDatabaseId, TestContainerId, "test-conversation"));
    }

    [Fact]
    [Trait("Category", "CosmosDB")]
    public void Constructor_WithEmptyConversationId_ShouldThrowArgumentException()
    {
        // Arrange & Act & Assert
        SkipIfEmulatorNotAvailable();

        Assert.Throws<ArgumentException>(() =>
            new CosmosChatMessageStore(this._connectionString, TestDatabaseId, TestContainerId, ""));
    }

    #endregion

    #region AddMessagesAsync Tests

    [Fact]
    [Trait("Category", "CosmosDB")]
    public async Task AddMessagesAsync_WithSingleMessage_ShouldAddMessageAsync()
    {
        // Arrange
        this.SkipIfEmulatorNotAvailable();
        var conversationId = Guid.NewGuid().ToString();
        using var store = new CosmosChatMessageStore(this._connectionString, TestDatabaseId, TestContainerId, conversationId);
        var message = new ChatMessage(ChatRole.User, "Hello, world!");

        // Act
        await store.AddMessagesAsync([message]);

        // Wait a moment for eventual consistency
        await Task.Delay(100);

        // Assert
        var messages = await store.GetMessagesAsync();
        var messageList = messages.ToList();

        // Simple assertion - if this fails, we know the deserialization is the issue
        if (messageList.Count == 0)
        {
            // Let's check if we can find ANY items in the container for this conversation
            var directQuery = new QueryDefinition("SELECT VALUE COUNT(1) FROM c WHERE c.conversationId = @conversationId")
                .WithParameter("@conversationId", conversationId);
            var countIterator = this._setupClient!.GetDatabase(TestDatabaseId).GetContainer(TestContainerId)
                .GetItemQueryIterator<int>(directQuery, requestOptions: new QueryRequestOptions
                {
                    PartitionKey = new PartitionKey(conversationId)
                });

            var countResponse = await countIterator.ReadNextAsync();
            var count = countResponse.FirstOrDefault();

            // Debug: Let's see what the raw query returns
            var rawQuery = new QueryDefinition("SELECT * FROM c WHERE c.conversationId = @conversationId")
                .WithParameter("@conversationId", conversationId);
            var rawIterator = this._setupClient!.GetDatabase(TestDatabaseId).GetContainer(TestContainerId)
                .GetItemQueryIterator<dynamic>(rawQuery, requestOptions: new QueryRequestOptions
                {
                    PartitionKey = new PartitionKey(conversationId)
                });

            List<dynamic> rawResults = new List<dynamic>();
            while (rawIterator.HasMoreResults)
            {
                var rawResponse = await rawIterator.ReadNextAsync();
                rawResults.AddRange(rawResponse);
            }

            string rawJson = rawResults.Count > 0 ? Newtonsoft.Json.JsonConvert.SerializeObject(rawResults[0], Newtonsoft.Json.Formatting.Indented) : "null";
            Assert.Fail($"GetMessagesAsync returned 0 messages, but direct count query found {count} items for conversation {conversationId}. Raw document: {rawJson}");
        }

        Assert.Single(messageList);
        Assert.Equal("Hello, world!", messageList[0].Text);
        Assert.Equal(ChatRole.User, messageList[0].Role);
    }

    [Fact]
    [Trait("Category", "CosmosDB")]
    public async Task AddMessagesAsync_WithMultipleMessages_ShouldAddAllMessagesAsync()
    {
        // Arrange
        SkipIfEmulatorNotAvailable();
        var conversationId = Guid.NewGuid().ToString();
        using var store = new CosmosChatMessageStore(this._connectionString, TestDatabaseId, TestContainerId, conversationId);
        var messages = new[]
        {
            new ChatMessage(ChatRole.User, "First message"),
            new ChatMessage(ChatRole.Assistant, "Second message"),
            new ChatMessage(ChatRole.User, "Third message")
        };

        // Act
        await store.AddMessagesAsync(messages);

        // Assert
        var retrievedMessages = await store.GetMessagesAsync();
        var messageList = retrievedMessages.ToList();
        Assert.Equal(3, messageList.Count);
        Assert.Equal("First message", messageList[0].Text);
        Assert.Equal("Second message", messageList[1].Text);
        Assert.Equal("Third message", messageList[2].Text);
    }

    #endregion

    #region GetMessagesAsync Tests

    [Fact]
    [Trait("Category", "CosmosDB")]
    public async Task GetMessagesAsync_WithNoMessages_ShouldReturnEmptyAsync()
    {
        // Arrange
        SkipIfEmulatorNotAvailable();
        using var store = new CosmosChatMessageStore(this._connectionString, TestDatabaseId, TestContainerId, Guid.NewGuid().ToString());

        // Act
        var messages = await store.GetMessagesAsync();

        // Assert
        Assert.Empty(messages);
    }

    [Fact]
    [Trait("Category", "CosmosDB")]
    public async Task GetMessagesAsync_WithConversationIsolation_ShouldOnlyReturnMessagesForConversationAsync()
    {
        // Arrange
        SkipIfEmulatorNotAvailable();
        var conversation1 = Guid.NewGuid().ToString();
        var conversation2 = Guid.NewGuid().ToString();

        using var store1 = new CosmosChatMessageStore(this._connectionString, TestDatabaseId, TestContainerId, conversation1);
        using var store2 = new CosmosChatMessageStore(this._connectionString, TestDatabaseId, TestContainerId, conversation2);

        await store1.AddMessagesAsync([new ChatMessage(ChatRole.User, "Message for conversation 1")]);
        await store2.AddMessagesAsync([new ChatMessage(ChatRole.User, "Message for conversation 2")]);

        // Act
        var messages1 = await store1.GetMessagesAsync();
        var messages2 = await store2.GetMessagesAsync();

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

    [Fact]
    [Trait("Category", "CosmosDB")]
    public async Task FullWorkflow_AddAndGet_ShouldWorkCorrectlyAsync()
    {
        // Arrange
        SkipIfEmulatorNotAvailable();
        using var originalStore = new CosmosChatMessageStore(this._connectionString, TestDatabaseId, TestContainerId, "test-conversation");

        var messages = new[]
        {
            new ChatMessage(ChatRole.System, "You are a helpful assistant."),
            new ChatMessage(ChatRole.User, "Hello!"),
            new ChatMessage(ChatRole.Assistant, "Hi there! How can I help you today?"),
            new ChatMessage(ChatRole.User, "What's the weather like?"),
            new ChatMessage(ChatRole.Assistant, "I'm sorry, I don't have access to current weather data.")
        };

        // Act 1: Add messages
        await originalStore.AddMessagesAsync(messages);

        // Act 2: Verify messages were added
        var retrievedMessages = await originalStore.GetMessagesAsync();
        var retrievedList = retrievedMessages.ToList();
        Assert.Equal(5, retrievedList.Count);

        // Act 3: Create new store instance for same conversation (test persistence)
        using var newStore = new CosmosChatMessageStore(this._connectionString, TestDatabaseId, TestContainerId, "test-conversation");
        var persistedMessages = await newStore.GetMessagesAsync();
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

    [Fact]
    [Trait("Category", "CosmosDB")]
    public void Dispose_AfterUse_ShouldNotThrow()
    {
        // Arrange
        SkipIfEmulatorNotAvailable();
        var store = new CosmosChatMessageStore(this._connectionString, TestDatabaseId, TestContainerId, Guid.NewGuid().ToString());

        // Act & Assert
        store.Dispose(); // Should not throw
    }

    [Fact]
    [Trait("Category", "CosmosDB")]
    public void Dispose_MultipleCalls_ShouldNotThrow()
    {
        // Arrange
        SkipIfEmulatorNotAvailable();
        var store = new CosmosChatMessageStore(this._connectionString, TestDatabaseId, TestContainerId, Guid.NewGuid().ToString());

        // Act & Assert
        store.Dispose(); // First call
        store.Dispose(); // Second call - should not throw
    }

    #endregion
}
