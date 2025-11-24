// Copyright (c) Microsoft. All rights reserved.

namespace Microsoft.Agents.AI.Hosting.OpenAI.UnitTests;

/// <summary>
/// Unit tests for IdGenerator.
/// </summary>
public sealed class IdGeneratorTests
{
    [Fact]
    public void Constructor_WithResponseIdAndConversationId_InitializesCorrectly()
    {
        // Arrange
        const string ResponseId = "resp_test123";
        const string ConversationId = "conv_test456";

        // Act
        var generator = new IdGenerator(ResponseId, ConversationId);

        // Assert
        Assert.Equal(ResponseId, generator.ResponseId);
        Assert.Equal(ConversationId, generator.ConversationId);
    }

    [Fact]
    public void Constructor_WithNullIds_GeneratesNewIds()
    {
        // Arrange & Act
        var generator = new IdGenerator(null, null);

        // Assert
        Assert.NotNull(generator.ResponseId);
        Assert.NotNull(generator.ConversationId);
        Assert.StartsWith("resp_", generator.ResponseId);
        Assert.StartsWith("conv_", generator.ConversationId);
    }

    [Fact]
    public void Constructor_WithRandomSeed_GeneratesDeterministicIds()
    {
        // Arrange
        const int Seed = 12345;

        // Act
        var generator1 = new IdGenerator(null, null, Seed);
        var generator2 = new IdGenerator(null, null, Seed);

        // Assert
        Assert.Equal(generator1.ResponseId, generator2.ResponseId);
        Assert.Equal(generator1.ConversationId, generator2.ConversationId);
    }

    [Fact]
    public void Constructor_WithDifferentRandomSeeds_GeneratesDifferentIds()
    {
        // Arrange
        const int Seed1 = 12345;
        const int Seed2 = 54321;

        // Act
        var generator1 = new IdGenerator(null, null, Seed1);
        var generator2 = new IdGenerator(null, null, Seed2);

        // Assert
        Assert.NotEqual(generator1.ResponseId, generator2.ResponseId);
        Assert.NotEqual(generator1.ConversationId, generator2.ConversationId);
    }

    [Fact]
    public void Generate_WithCategory_IncludesCategory()
    {
        // Arrange
        var generator = new IdGenerator("resp_test", "conv_test");

        // Act
        string id = generator.Generate("test_category");

        // Assert
        Assert.NotNull(id);
        Assert.StartsWith("test_category_", id);
    }

    [Fact]
    public void Generate_WithoutCategory_UsesDefaultPrefix()
    {
        // Arrange
        var generator = new IdGenerator("resp_test", "conv_test");

        // Act
        string id = generator.Generate();

        // Assert
        Assert.NotNull(id);
        Assert.StartsWith("id_", id);
    }

    [Fact]
    public void Generate_WithSeed_ProducesDeterministicResults()
    {
        // Arrange
        const int Seed = 12345;
        var generator = new IdGenerator("resp_test", "conv_test", Seed);

        // Act
        string id1 = generator.Generate("test");
        string id2 = generator.Generate("test");
        string id3 = generator.Generate("test");

        // Assert - IDs should be different but deterministic
        Assert.NotEqual(id1, id2);
        Assert.NotEqual(id2, id3);
        Assert.NotEqual(id1, id3);

        // Verify deterministic by creating a new generator with same seed
        var generator2 = new IdGenerator("resp_test", "conv_test", Seed);
        string id1_2 = generator2.Generate("test");
        string id2_2 = generator2.Generate("test");
        string id3_2 = generator2.Generate("test");

        Assert.Equal(id1, id1_2);
        Assert.Equal(id2, id2_2);
        Assert.Equal(id3, id3_2);
    }

    [Fact]
    public void GenerateFunctionCallId_ReturnsIdWithFuncPrefix()
    {
        // Arrange
        var generator = new IdGenerator("resp_test", "conv_test");

        // Act
        string id = generator.GenerateFunctionCallId();

        // Assert
        Assert.NotNull(id);
        Assert.StartsWith("func_", id);
    }

    [Fact]
    public void GenerateFunctionOutputId_ReturnsIdWithFuncoutPrefix()
    {
        // Arrange
        var generator = new IdGenerator("resp_test", "conv_test");

        // Act
        string id = generator.GenerateFunctionOutputId();

        // Assert
        Assert.NotNull(id);
        Assert.StartsWith("funcout_", id);
    }

    [Fact]
    public void GenerateMessageId_ReturnsIdWithMsgPrefix()
    {
        // Arrange
        var generator = new IdGenerator("resp_test", "conv_test");

        // Act
        string id = generator.GenerateMessageId();

        // Assert
        Assert.NotNull(id);
        Assert.StartsWith("msg_", id);
    }

    [Fact]
    public void GenerateReasoningId_ReturnsIdWithRsPrefix()
    {
        // Arrange
        var generator = new IdGenerator("resp_test", "conv_test");

        // Act
        string id = generator.GenerateReasoningId();

        // Assert
        Assert.NotNull(id);
        Assert.StartsWith("rs_", id);
    }

    [Fact]
    public void Generate_MultipleInvocations_ProducesUniqueIds()
    {
        // Arrange
        var generator = new IdGenerator("resp_test", "conv_test");
        var ids = new System.Collections.Generic.HashSet<string>();

        // Act
        for (int i = 0; i < 100; i++)
        {
            string id = generator.Generate("test");
            ids.Add(id);
        }

        // Assert
        Assert.Equal(100, ids.Count); // All IDs should be unique
    }

    [Fact]
    public void Generate_SharesPartitionKey()
    {
        // Arrange
        const string ConversationId = "conv_1234567890abcdef1234567890abcdef1234567890abcdef";
        var generator = new IdGenerator("resp_test", ConversationId, randomSeed: 12345);

        // Act
        string id1 = generator.Generate("msg");
        string id2 = generator.Generate("msg");

        // Assert - Both IDs should share the same partition key
        Assert.NotEqual(id1, id2);
        Assert.NotNull(id1);
        Assert.NotNull(id2);

        // Format is: msg_<entropy><partitionKey> where entropy = 32 chars and partitionKey = 16 chars
        // Both IDs from the same generator should share the partition key
        Assert.StartsWith("msg_", id1);
        Assert.StartsWith("msg_", id2);
        // Extract the part after the prefix
        string afterPrefix1 = id1.Substring(4); // Skip "msg_"
        string afterPrefix2 = id2.Substring(4);
        // Both should have the same length (32 + 16 = 48)
        Assert.Equal(48, afterPrefix1.Length);
        Assert.Equal(48, afterPrefix2.Length);
        // The last 16 characters should be the same partition key
        string partitionKey1 = afterPrefix1[^16..];
        string partitionKey2 = afterPrefix2[^16..];
        Assert.Equal(partitionKey1, partitionKey2);
    }

    [Fact]
    public void From_WithConversationInRequest_UsesConversationId()
    {
        // Arrange
        var request = new Responses.Models.CreateResponse
        {
            Model = "test-model",
            Input = Responses.Models.ResponseInput.FromText("test"),
            Conversation = new Responses.Models.ConversationReference
            {
                Id = "conv_fromrequest"
            }
        };

        // Act
        IdGenerator generator = IdGenerator.From(request);

        // Assert
        Assert.Equal("conv_fromrequest", generator.ConversationId);
        Assert.NotNull(generator.ResponseId);
        Assert.StartsWith("resp_", generator.ResponseId);
    }

    [Fact]
    public void From_WithResponseIdInMetadata_UsesResponseId()
    {
        // Arrange
        var request = new Responses.Models.CreateResponse
        {
            Model = "test-model",
            Input = Responses.Models.ResponseInput.FromText("test"),
            Metadata = new System.Collections.Generic.Dictionary<string, string>
            {
                ["response_id"] = "resp_metadata123"
            }
        };

        // Act
        IdGenerator generator = IdGenerator.From(request);

        // Assert
        Assert.Equal("resp_metadata123", generator.ResponseId);
    }

    [Fact]
    public void From_WithoutIdsInRequest_GeneratesNewIds()
    {
        // Arrange
        var request = new Responses.Models.CreateResponse
        {
            Model = "test-model",
            Input = Responses.Models.ResponseInput.FromText("test")
        };

        // Act
        IdGenerator generator = IdGenerator.From(request);

        // Assert
        Assert.NotNull(generator.ResponseId);
        Assert.NotNull(generator.ConversationId);
        Assert.StartsWith("resp_", generator.ResponseId);
        Assert.StartsWith("conv_", generator.ConversationId);
    }
}
