// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Text.Json;
using Microsoft.Agents.AI.Abstractions.UnitTests.Models;

namespace Microsoft.Agents.AI.Abstractions.UnitTests;

/// <summary>
/// Contains tests for the <see cref="AgentSessionStateBag"/> class.
/// </summary>
public sealed class AgentSessionStateBagTests
{
    #region Constructor Tests

    [Fact]
    public void Constructor_Default_CreatesEmptyStateBag()
    {
        // Act
        var stateBag = new AgentSessionStateBag();

        // Assert
        Assert.False(stateBag.TryGetValue<string>("nonexistent", out _));
    }

    #endregion

    #region SetValue Tests

    [Fact]
    public void SetValue_WithValidKeyAndValue_StoresValue()
    {
        // Arrange
        var stateBag = new AgentSessionStateBag();

        // Act
        stateBag.SetValue("key1", "value1");

        // Assert
        Assert.True(stateBag.TryGetValue<string>("key1", out var result));
        Assert.Equal("value1", result);
    }

    [Fact]
    public void SetValue_WithNullKey_ThrowsArgumentException()
    {
        // Arrange
        var stateBag = new AgentSessionStateBag();

        // Act & Assert
        Assert.Throws<ArgumentNullException>(() => stateBag.SetValue(null!, "value"));
    }

    [Fact]
    public void SetValue_WithEmptyKey_ThrowsArgumentException()
    {
        // Arrange
        var stateBag = new AgentSessionStateBag();

        // Act & Assert
        Assert.Throws<ArgumentException>(() => stateBag.SetValue("", "value"));
    }

    [Fact]
    public void SetValue_WithWhitespaceKey_ThrowsArgumentException()
    {
        // Arrange
        var stateBag = new AgentSessionStateBag();

        // Act & Assert
        Assert.Throws<ArgumentException>(() => stateBag.SetValue("   ", "value"));
    }

    [Fact]
    public void SetValue_OverwritesExistingValue()
    {
        // Arrange
        var stateBag = new AgentSessionStateBag();
        stateBag.SetValue("key1", "originalValue");

        // Act
        stateBag.SetValue("key1", "newValue");

        // Assert
        Assert.Equal("newValue", stateBag.GetValue<string>("key1"));
    }

    #endregion

    #region GetValue Tests

    [Fact]
    public void GetValue_WithExistingKey_ReturnsValue()
    {
        // Arrange
        var stateBag = new AgentSessionStateBag();
        stateBag.SetValue("key1", "value1");

        // Act
        var result = stateBag.GetValue<string>("key1");

        // Assert
        Assert.Equal("value1", result);
    }

    [Fact]
    public void GetValue_WithNonexistentKey_ReturnsNull()
    {
        // Arrange
        var stateBag = new AgentSessionStateBag();

        // Act
        var result = stateBag.GetValue<string>("nonexistent");

        // Assert
        Assert.Null(result);
    }

    [Fact]
    public void GetValue_WithNullKey_ThrowsArgumentException()
    {
        // Arrange
        var stateBag = new AgentSessionStateBag();

        // Act & Assert
        Assert.Throws<ArgumentNullException>(() => stateBag.GetValue<string>(null!));
    }

    [Fact]
    public void GetValue_WithEmptyKey_ThrowsArgumentException()
    {
        // Arrange
        var stateBag = new AgentSessionStateBag();

        // Act & Assert
        Assert.Throws<ArgumentException>(() => stateBag.GetValue<string>(""));
    }

    [Fact]
    public void GetValue_CachesDeserializedValue()
    {
        // Arrange
        var stateBag = new AgentSessionStateBag();
        stateBag.SetValue("key1", "value1");

        // Act
        var result1 = stateBag.GetValue<string>("key1");
        var result2 = stateBag.GetValue<string>("key1");

        // Assert
        Assert.Same(result1, result2);
    }

    #endregion

    #region TryGetValue Tests

    [Fact]
    public void TryGetValue_WithExistingKey_ReturnsTrueAndValue()
    {
        // Arrange
        var stateBag = new AgentSessionStateBag();
        stateBag.SetValue("key1", "value1");

        // Act
        var found = stateBag.TryGetValue<string>("key1", out var result);

        // Assert
        Assert.True(found);
        Assert.Equal("value1", result);
    }

    [Fact]
    public void TryGetValue_WithNonexistentKey_ReturnsFalseAndNull()
    {
        // Arrange
        var stateBag = new AgentSessionStateBag();

        // Act
        var found = stateBag.TryGetValue<string>("nonexistent", out var result);

        // Assert
        Assert.False(found);
        Assert.Null(result);
    }

    [Fact]
    public void TryGetValue_WithNullKey_ThrowsArgumentException()
    {
        // Arrange
        var stateBag = new AgentSessionStateBag();

        // Act & Assert
        Assert.Throws<ArgumentNullException>(() => stateBag.TryGetValue<string>(null!, out _));
    }

    [Fact]
    public void TryGetValue_WithEmptyKey_ThrowsArgumentException()
    {
        // Arrange
        var stateBag = new AgentSessionStateBag();

        // Act & Assert
        Assert.Throws<ArgumentException>(() => stateBag.TryGetValue<string>("", out _));
    }

    #endregion

    #region Null Value Tests

    [Fact]
    public void SetValue_WithNullValue_StoresNull()
    {
        // Arrange
        var stateBag = new AgentSessionStateBag();

        // Act
        stateBag.SetValue<string>("key1", null);

        // Assert
        Assert.Equal(1, stateBag.Count);
    }

    [Fact]
    public void TryGetValue_WithNullValue_ReturnsTrueAndNull()
    {
        // Arrange
        var stateBag = new AgentSessionStateBag();
        stateBag.SetValue<string>("key1", null);

        // Act
        var found = stateBag.TryGetValue<string>("key1", out var result);

        // Assert
        Assert.True(found);
        Assert.Null(result);
    }

    [Fact]
    public void GetValue_WithNullValue_ReturnsNull()
    {
        // Arrange
        var stateBag = new AgentSessionStateBag();
        stateBag.SetValue<string>("key1", null);

        // Act
        var result = stateBag.GetValue<string>("key1");

        // Assert
        Assert.Null(result);
    }

    [Fact]
    public void SetValue_OverwriteWithNull_ReturnsNull()
    {
        // Arrange
        var stateBag = new AgentSessionStateBag();
        stateBag.SetValue("key1", "value1");

        // Act
        stateBag.SetValue<string>("key1", null);

        // Assert
        Assert.True(stateBag.TryGetValue<string>("key1", out var result));
        Assert.Null(result);
    }

    [Fact]
    public void SetValue_OverwriteNullWithValue_ReturnsValue()
    {
        // Arrange
        var stateBag = new AgentSessionStateBag();
        stateBag.SetValue<string>("key1", null);

        // Act
        stateBag.SetValue("key1", "newValue");

        // Assert
        Assert.True(stateBag.TryGetValue<string>("key1", out var result));
        Assert.Equal("newValue", result);
    }

    [Fact]
    public void SerializeDeserialize_WithNullValue_SerializesAsNull()
    {
        // Arrange
        var stateBag = new AgentSessionStateBag();
        stateBag.SetValue<string>("nullKey", null);

        // Act
        var json = stateBag.Serialize();

        // Assert - null values are serialized as JSON null
        Assert.Equal(JsonValueKind.Object, json.ValueKind);
        Assert.True(json.TryGetProperty("nullKey", out var nullElement));
        Assert.Equal(JsonValueKind.Null, nullElement.ValueKind);
    }

    #endregion

    #region TryRemoveValue Tests

    [Fact]
    public void TryRemoveValue_ExistingKey_ReturnsTrueAndRemoves()
    {
        // Arrange
        var stateBag = new AgentSessionStateBag();
        stateBag.SetValue("key1", "value1");

        // Act
        var removed = stateBag.TryRemoveValue("key1");

        // Assert
        Assert.True(removed);
        Assert.Equal(0, stateBag.Count);
        Assert.False(stateBag.TryGetValue<string>("key1", out _));
    }

    [Fact]
    public void TryRemoveValue_NonexistentKey_ReturnsFalse()
    {
        // Arrange
        var stateBag = new AgentSessionStateBag();

        // Act
        var removed = stateBag.TryRemoveValue("nonexistent");

        // Assert
        Assert.False(removed);
    }

    [Fact]
    public void TryRemoveValue_WithNullKey_ThrowsArgumentException()
    {
        // Arrange
        var stateBag = new AgentSessionStateBag();

        // Act & Assert
        Assert.Throws<ArgumentNullException>(() => stateBag.TryRemoveValue(null!));
    }

    [Fact]
    public void TryRemoveValue_WithEmptyKey_ThrowsArgumentException()
    {
        // Arrange
        var stateBag = new AgentSessionStateBag();

        // Act & Assert
        Assert.Throws<ArgumentException>(() => stateBag.TryRemoveValue(""));
    }

    [Fact]
    public void TryRemoveValue_WithWhitespaceKey_ThrowsArgumentException()
    {
        // Arrange
        var stateBag = new AgentSessionStateBag();

        // Act & Assert
        Assert.Throws<ArgumentException>(() => stateBag.TryRemoveValue("   "));
    }

    [Fact]
    public void TryRemoveValue_DoesNotAffectOtherKeys()
    {
        // Arrange
        var stateBag = new AgentSessionStateBag();
        stateBag.SetValue("key1", "value1");
        stateBag.SetValue("key2", "value2");

        // Act
        stateBag.TryRemoveValue("key1");

        // Assert
        Assert.Equal(1, stateBag.Count);
        Assert.False(stateBag.TryGetValue<string>("key1", out _));
        Assert.True(stateBag.TryGetValue<string>("key2", out var value));
        Assert.Equal("value2", value);
    }

    [Fact]
    public void TryRemoveValue_ThenSetValue_Works()
    {
        // Arrange
        var stateBag = new AgentSessionStateBag();
        stateBag.SetValue("key1", "original");

        // Act
        stateBag.TryRemoveValue("key1");
        stateBag.SetValue("key1", "replacement");

        // Assert
        Assert.True(stateBag.TryGetValue<string>("key1", out var result));
        Assert.Equal("replacement", result);
    }

    #endregion

    #region Serialize/Deserialize Tests

    [Fact]
    public void Serialize_EmptyStateBag_ReturnsEmptyObject()
    {
        // Arrange
        var stateBag = new AgentSessionStateBag();

        // Act
        var json = stateBag.Serialize();

        // Assert
        Assert.Equal(JsonValueKind.Object, json.ValueKind);
    }

    [Fact]
    public void Serialize_WithStringValue_ReturnsJsonWithValue()
    {
        // Arrange
        var stateBag = new AgentSessionStateBag();
        stateBag.SetValue("stringKey", "stringValue");

        // Act
        var json = stateBag.Serialize();

        // Assert
        Assert.Equal(JsonValueKind.Object, json.ValueKind);
        Assert.True(json.TryGetProperty("stringKey", out _));
    }

    [Fact]
    public void Deserialize_FromJsonDocument_ReturnsEmptyStateBag()
    {
        // Arrange
        var emptyJson = JsonDocument.Parse("{}").RootElement;

        // Act
        var stateBag = AgentSessionStateBag.Deserialize(emptyJson);

        // Assert
        Assert.False(stateBag.TryGetValue<string>("nonexistent", out _));
    }

    [Fact]
    public void Deserialize_NullElement_ReturnsEmptyStateBag()
    {
        // Arrange
        var nullJson = default(JsonElement);

        // Act
        var stateBag = AgentSessionStateBag.Deserialize(nullJson);

        // Assert
        Assert.False(stateBag.TryGetValue<string>("nonexistent", out _));
    }

    [Fact]
    public void SerializeDeserialize_WithStringValue_Roundtrips()
    {
        // Arrange
        var originalStateBag = new AgentSessionStateBag();
        originalStateBag.SetValue("stringKey", "stringValue");

        // Act
        var json = originalStateBag.Serialize();
        var restoredStateBag = AgentSessionStateBag.Deserialize(json);

        // Assert
        Assert.Equal("stringValue", restoredStateBag.GetValue<string>("stringKey"));
    }

    #endregion

    #region Thread Safety Tests

    [Fact]
    public async System.Threading.Tasks.Task SetValue_MultipleConcurrentWrites_DoesNotThrowAsync()
    {
        // Arrange
        var stateBag = new AgentSessionStateBag();
        var tasks = new System.Threading.Tasks.Task[100];

        // Act
        for (int i = 0; i < 100; i++)
        {
            int index = i;
            tasks[i] = System.Threading.Tasks.Task.Run(() => stateBag.SetValue($"key{index}", $"value{index}"));
        }

        await System.Threading.Tasks.Task.WhenAll(tasks);

        // Assert
        for (int i = 0; i < 100; i++)
        {
            Assert.True(stateBag.TryGetValue<string>($"key{i}", out var value));
            Assert.Equal($"value{i}", value);
        }
    }

    [Fact]
    public async System.Threading.Tasks.Task ConcurrentWritesAndSerialize_DoesNotThrowAsync()
    {
        // Arrange
        var stateBag = new AgentSessionStateBag();
        stateBag.SetValue("shared", "initial");
        var tasks = new System.Threading.Tasks.Task[100];

        // Act - concurrently write and serialize the same key
        for (int i = 0; i < 100; i++)
        {
            int index = i;
            tasks[i] = System.Threading.Tasks.Task.Run(() =>
            {
                stateBag.SetValue("shared", $"value{index}");
                _ = stateBag.Serialize();
            });
        }

        await System.Threading.Tasks.Task.WhenAll(tasks);

        // Assert - should have some value and serialize without error
        Assert.True(stateBag.TryGetValue<string>("shared", out var result));
        Assert.NotNull(result);
        var json = stateBag.Serialize();
        Assert.Equal(JsonValueKind.Object, json.ValueKind);
    }

    [Fact]
    public async System.Threading.Tasks.Task ConcurrentReadsAndWrites_DoesNotThrowAsync()
    {
        // Arrange
        var stateBag = new AgentSessionStateBag();
        stateBag.SetValue("key", "initial");
        var tasks = new System.Threading.Tasks.Task[200];

        // Act - half readers, half writers on the same key
        for (int i = 0; i < 200; i++)
        {
            int index = i;
            tasks[i] = (index % 2 == 0)
                ? System.Threading.Tasks.Task.Run(() => stateBag.GetValue<string>("key"))
                : System.Threading.Tasks.Task.Run(() => stateBag.SetValue("key", $"value{index}"));
        }

        await System.Threading.Tasks.Task.WhenAll(tasks);

        // Assert - should have a consistent value
        Assert.True(stateBag.TryGetValue<string>("key", out var result));
        Assert.NotNull(result);
    }

    #endregion

    #region Complex Object Tests

    [Fact]
    public void SetValue_WithComplexObject_StoresValue()
    {
        // Arrange
        var stateBag = new AgentSessionStateBag();
        var animal = new Animal { Id = 1, FullName = "Buddy", Species = Species.Bear };

        // Act
        stateBag.SetValue("animal", animal, TestJsonSerializerContext.Default.Options);

        // Assert
        Animal? result = stateBag.GetValue<Animal>("animal", TestJsonSerializerContext.Default.Options);
        Assert.NotNull(result);
        Assert.Equal(1, result.Id);
        Assert.Equal("Buddy", result.FullName);
        Assert.Equal(Species.Bear, result.Species);
    }

    [Fact]
    public void GetValue_WithComplexObject_CachesDeserializedValue()
    {
        // Arrange
        var stateBag = new AgentSessionStateBag();
        var animal = new Animal { Id = 2, FullName = "Whiskers", Species = Species.Tiger };
        stateBag.SetValue("animal", animal, TestJsonSerializerContext.Default.Options);

        // Act
        Animal? result1 = stateBag.GetValue<Animal>("animal", TestJsonSerializerContext.Default.Options);
        Animal? result2 = stateBag.GetValue<Animal>("animal", TestJsonSerializerContext.Default.Options);

        // Assert
        Assert.Same(result1, result2);
    }

    [Fact]
    public void TryGetValue_WithComplexObject_ReturnsTrueAndValue()
    {
        // Arrange
        var stateBag = new AgentSessionStateBag();
        var animal = new Animal { Id = 3, FullName = "Goldie", Species = Species.Walrus };
        stateBag.SetValue("animal", animal, TestJsonSerializerContext.Default.Options);

        // Act
        bool found = stateBag.TryGetValue("animal", out Animal? result, TestJsonSerializerContext.Default.Options);

        // Assert
        Assert.True(found);
        Assert.NotNull(result);
        Assert.Equal(3, result.Id);
        Assert.Equal("Goldie", result.FullName);
        Assert.Equal(Species.Walrus, result.Species);
    }

    [Fact]
    public void SerializeDeserialize_WithComplexObject_Roundtrips()
    {
        // Arrange
        var originalStateBag = new AgentSessionStateBag();
        var animal = new Animal { Id = 4, FullName = "Polly", Species = Species.Bear };
        originalStateBag.SetValue("animal", animal, TestJsonSerializerContext.Default.Options);

        // Act
        JsonElement json = originalStateBag.Serialize();
        AgentSessionStateBag restoredStateBag = AgentSessionStateBag.Deserialize(json);

        // Assert
        Animal? restoredAnimal = restoredStateBag.GetValue<Animal>("animal", TestJsonSerializerContext.Default.Options);
        Assert.NotNull(restoredAnimal);
        Assert.Equal(4, restoredAnimal.Id);
        Assert.Equal("Polly", restoredAnimal.FullName);
        Assert.Equal(Species.Bear, restoredAnimal.Species);
    }

    [Fact]
    public void Serialize_WithComplexObject_ReturnsJsonWithProperties()
    {
        // Arrange
        var stateBag = new AgentSessionStateBag();
        var animal = new Animal { Id = 7, FullName = "Spot", Species = Species.Walrus };
        stateBag.SetValue("animal", animal, TestJsonSerializerContext.Default.Options);

        // Act
        JsonElement json = stateBag.Serialize();

        // Assert
        Assert.Equal(JsonValueKind.Object, json.ValueKind);
        Assert.True(json.TryGetProperty("animal", out JsonElement animalElement));
        Assert.Equal(JsonValueKind.Object, animalElement.ValueKind);
        Assert.Equal(7, animalElement.GetProperty("id").GetInt32());
        Assert.Equal("Spot", animalElement.GetProperty("fullName").GetString());
        Assert.Equal("Walrus", animalElement.GetProperty("species").GetString());
    }

    #endregion

    #region Type Mismatch Tests

    [Fact]
    public void TryGetValue_WithDifferentTypeAfterSet_ReturnsFalse()
    {
        // Arrange
        var stateBag = new AgentSessionStateBag();
        stateBag.SetValue("key1", "hello");

        // Act
        var found = stateBag.TryGetValue<Animal>("key1", out var result, TestJsonSerializerContext.Default.Options);

        // Assert
        Assert.False(found);
        Assert.Null(result);
    }

    [Fact]
    public void GetValue_WithDifferentTypeAfterSet_ThrowsInvalidOperationException()
    {
        // Arrange
        var stateBag = new AgentSessionStateBag();
        stateBag.SetValue("key1", "hello");

        // Act & Assert
        Assert.Throws<InvalidOperationException>(() => stateBag.GetValue<Animal>("key1", TestJsonSerializerContext.Default.Options));
    }

    [Fact]
    public void TryGetValue_WithDifferentTypeAfterDeserializedRead_ReturnsFalse()
    {
        // Arrange
        var stateBag = new AgentSessionStateBag();
        stateBag.SetValue("key1", "hello");

        // First read caches the value as string
        var cachedValue = stateBag.GetValue<string>("key1");
        Assert.Equal("hello", cachedValue);

        // Act - request as a different type
        var found = stateBag.TryGetValue<Animal>("key1", out var result, TestJsonSerializerContext.Default.Options);

        // Assert
        Assert.False(found);
        Assert.Null(result);
    }

    [Fact]
    public void GetValue_WithDifferentTypeAfterDeserializedRoundtrip_ThrowsInvalidOperationException()
    {
        // Arrange
        var originalStateBag = new AgentSessionStateBag();
        originalStateBag.SetValue("key1", "hello");

        // Round-trip through serialization
        var json = originalStateBag.Serialize();
        var restoredStateBag = AgentSessionStateBag.Deserialize(json);

        // First read caches the value as string
        var cachedValue = restoredStateBag.GetValue<string>("key1");
        Assert.Equal("hello", cachedValue);

        // Act & Assert - request as a different type
        Assert.Throws<InvalidOperationException>(() => restoredStateBag.GetValue<Animal>("key1", TestJsonSerializerContext.Default.Options));
    }

    [Fact]
    public void TryGetValue_ComplexTypeAfterSetString_ReturnsFalse()
    {
        // Arrange
        var stateBag = new AgentSessionStateBag();
        stateBag.SetValue("animal", "not an animal");

        // Act
        var found = stateBag.TryGetValue<Animal>("animal", out var result, TestJsonSerializerContext.Default.Options);

        // Assert
        Assert.False(found);
        Assert.Null(result);
    }

    [Fact]
    public void GetValue_TypeMismatch_ExceptionMessageContainsBothTypeNames()
    {
        // Arrange
        var stateBag = new AgentSessionStateBag();
        stateBag.SetValue("key1", "hello");

        // Act
        var exception = Assert.Throws<InvalidOperationException>(() => stateBag.GetValue<Animal>("key1", TestJsonSerializerContext.Default.Options));

        // Assert
        Assert.Contains(typeof(string).FullName!, exception.Message);
        Assert.Contains(typeof(Animal).FullName!, exception.Message);
    }

    #endregion

    #region JsonSerializer Integration Tests

    [Fact]
    public void JsonSerializerSerialize_EmptyStateBag_ReturnsEmptyObject()
    {
        // Arrange
        var stateBag = new AgentSessionStateBag();

        // Act
        var json = JsonSerializer.Serialize(stateBag, AgentAbstractionsJsonUtilities.DefaultOptions);

        // Assert
        Assert.Equal("{}", json);
    }

    [Fact]
    public void JsonSerializerSerialize_WithStringValue_ProducesSameOutputAsSerializeMethod()
    {
        // Arrange
        var stateBag = new AgentSessionStateBag();
        stateBag.SetValue("stringKey", "stringValue");

        // Act
        var jsonFromSerializer = JsonSerializer.Serialize(stateBag, AgentAbstractionsJsonUtilities.DefaultOptions);
        var jsonFromMethod = stateBag.Serialize().GetRawText();

        // Assert
        Assert.Equal(jsonFromMethod, jsonFromSerializer);
    }

    [Fact]
    public void JsonSerializerRoundtrip_WithStringValue_PreservesData()
    {
        // Arrange
        var stateBag = new AgentSessionStateBag();
        stateBag.SetValue("greeting", "hello world");

        // Act
        var json = JsonSerializer.Serialize(stateBag, AgentAbstractionsJsonUtilities.DefaultOptions);
        var restored = JsonSerializer.Deserialize<AgentSessionStateBag>(json, AgentAbstractionsJsonUtilities.DefaultOptions);

        // Assert
        Assert.NotNull(restored);
        Assert.Equal("hello world", restored!.GetValue<string>("greeting"));
    }

    [Fact]
    public void JsonSerializerRoundtrip_WithComplexObject_PreservesData()
    {
        // Arrange
        var stateBag = new AgentSessionStateBag();
        var animal = new Animal { Id = 10, FullName = "Rex", Species = Species.Tiger };
        stateBag.SetValue("animal", animal, TestJsonSerializerContext.Default.Options);

        // Act
        var json = JsonSerializer.Serialize(stateBag, AgentAbstractionsJsonUtilities.DefaultOptions);
        var restored = JsonSerializer.Deserialize<AgentSessionStateBag>(json, AgentAbstractionsJsonUtilities.DefaultOptions);

        // Assert
        Assert.NotNull(restored);
        var restoredAnimal = restored!.GetValue<Animal>("animal", TestJsonSerializerContext.Default.Options);
        Assert.NotNull(restoredAnimal);
        Assert.Equal(10, restoredAnimal!.Id);
        Assert.Equal("Rex", restoredAnimal.FullName);
        Assert.Equal(Species.Tiger, restoredAnimal.Species);
    }

    [Fact]
    public void JsonSerializerDeserialize_NullJson_ReturnsNull()
    {
        // Arrange
        const string Json = "null";

        // Act
        var stateBag = JsonSerializer.Deserialize<AgentSessionStateBag>(Json, AgentAbstractionsJsonUtilities.DefaultOptions);

        // Assert
        Assert.Null(stateBag);
    }

#if NET10_0_OR_GREATER
    [Fact]
    public void JsonSerializerSerialize_WithUnknownType_Throws()
    {
        // Arrange
        var stateBag = new AgentSessionStateBag();
        stateBag.SetValue("key", new { Name = "Test" }); // Anonymous type which cannot be deserialized

        // Act & Assert
        Assert.Throws<NotSupportedException>(() => JsonSerializer.Serialize(stateBag, AgentAbstractionsJsonUtilities.DefaultOptions));
    }
#endif

    #endregion
}
