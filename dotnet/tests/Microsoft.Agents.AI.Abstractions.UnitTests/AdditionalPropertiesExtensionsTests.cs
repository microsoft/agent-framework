// Copyright (c) Microsoft. All rights reserved.

using System;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Abstractions.UnitTests;

/// <summary>
/// Contains tests for the <see cref="AdditionalPropertiesExtensions"/> class.
/// </summary>
public sealed class AdditionalPropertiesExtensionsTests
{
    #region Add Method Tests

    [Fact]
    public void Add_WithValidValue_StoresValueUsingTypeName()
    {
        // Arrange
        AdditionalPropertiesDictionary additionalProperties = new();
        TestClass value = new() { Name = "Test" };

        // Act
        additionalProperties.Add(value);

        // Assert
        Assert.True(additionalProperties.ContainsKey(typeof(TestClass).FullName!));
        Assert.Same(value, additionalProperties[typeof(TestClass).FullName!]);
    }

    [Fact]
    public void Add_WithNullDictionary_ThrowsArgumentNullException()
    {
        // Arrange
        AdditionalPropertiesDictionary? additionalProperties = null;
        TestClass value = new() { Name = "Test" };

        // Act & Assert
        Assert.Throws<ArgumentNullException>(() => additionalProperties!.Add(value));
    }

    [Fact]
    public void Add_WithStringValue_StoresValueCorrectly()
    {
        // Arrange
        AdditionalPropertiesDictionary additionalProperties = new();
        const string Value = "test string";

        // Act
        additionalProperties.Add(Value);

        // Assert
        Assert.True(additionalProperties.ContainsKey(typeof(string).FullName!));
        Assert.Equal(Value, additionalProperties[typeof(string).FullName!]);
    }

    [Fact]
    public void Add_WithIntValue_StoresValueCorrectly()
    {
        // Arrange
        AdditionalPropertiesDictionary additionalProperties = new();
        const int Value = 42;

        // Act
        additionalProperties.Add(Value);

        // Assert
        Assert.True(additionalProperties.ContainsKey(typeof(int).FullName!));
        Assert.Equal(Value, additionalProperties[typeof(int).FullName!]);
    }

    [Fact]
    public void Add_ThrowsArgumentException_WhenSameTypeAddedTwice()
    {
        // Arrange
        AdditionalPropertiesDictionary additionalProperties = new();
        TestClass firstValue = new() { Name = "First" };
        TestClass secondValue = new() { Name = "Second" };
        additionalProperties.Add(firstValue);

        // Act & Assert
        Assert.Throws<ArgumentException>(() => additionalProperties.Add(secondValue));
    }

    [Fact]
    public void Add_WithMultipleDifferentTypes_StoresAllValues()
    {
        // Arrange
        AdditionalPropertiesDictionary additionalProperties = new();
        TestClass testClassValue = new() { Name = "Test" };
        AnotherTestClass anotherValue = new() { Id = 123 };
        const string StringValue = "test";

        // Act
        additionalProperties.Add(testClassValue);
        additionalProperties.Add(anotherValue);
        additionalProperties.Add(StringValue);

        // Assert
        Assert.Equal(3, additionalProperties.Count);
        Assert.Same(testClassValue, additionalProperties[typeof(TestClass).FullName!]);
        Assert.Same(anotherValue, additionalProperties[typeof(AnotherTestClass).FullName!]);
        Assert.Equal(StringValue, additionalProperties[typeof(string).FullName!]);
    }

    #endregion

    #region TryAdd Method Tests

    [Fact]
    public void TryAdd_WithValidValue_ReturnsTrueAndStoresValue()
    {
        // Arrange
        AdditionalPropertiesDictionary additionalProperties = new();
        TestClass value = new() { Name = "Test" };

        // Act
        bool result = additionalProperties.TryAdd(value);

        // Assert
        Assert.True(result);
        Assert.True(additionalProperties.ContainsKey(typeof(TestClass).FullName!));
        Assert.Same(value, additionalProperties[typeof(TestClass).FullName!]);
    }

    [Fact]
    public void TryAdd_WithNullDictionary_ThrowsArgumentNullException()
    {
        // Arrange
        AdditionalPropertiesDictionary? additionalProperties = null;
        TestClass value = new() { Name = "Test" };

        // Act & Assert
        Assert.Throws<ArgumentNullException>(() => additionalProperties!.TryAdd(value));
    }

    [Fact]
    public void TryAdd_WithExistingType_ReturnsFalseAndKeepsOriginalValue()
    {
        // Arrange
        AdditionalPropertiesDictionary additionalProperties = new();
        TestClass firstValue = new() { Name = "First" };
        TestClass secondValue = new() { Name = "Second" };
        additionalProperties.Add(firstValue);

        // Act
        bool result = additionalProperties.TryAdd(secondValue);

        // Assert
        Assert.False(result);
        Assert.Single(additionalProperties);
        Assert.Same(firstValue, additionalProperties[typeof(TestClass).FullName!]);
    }

    [Fact]
    public void TryAdd_WithStringValue_ReturnsTrueAndStoresValue()
    {
        // Arrange
        AdditionalPropertiesDictionary additionalProperties = new();
        const string Value = "test string";

        // Act
        bool result = additionalProperties.TryAdd(Value);

        // Assert
        Assert.True(result);
        Assert.True(additionalProperties.ContainsKey(typeof(string).FullName!));
        Assert.Equal(Value, additionalProperties[typeof(string).FullName!]);
    }

    [Fact]
    public void TryAdd_WithIntValue_ReturnsTrueAndStoresValue()
    {
        // Arrange
        AdditionalPropertiesDictionary additionalProperties = new();
        const int Value = 42;

        // Act
        bool result = additionalProperties.TryAdd(Value);

        // Assert
        Assert.True(result);
        Assert.True(additionalProperties.ContainsKey(typeof(int).FullName!));
        Assert.Equal(Value, additionalProperties[typeof(int).FullName!]);
    }

    [Fact]
    public void TryAdd_WithMultipleDifferentTypes_StoresAllValues()
    {
        // Arrange
        AdditionalPropertiesDictionary additionalProperties = new();
        TestClass testClassValue = new() { Name = "Test" };
        AnotherTestClass anotherValue = new() { Id = 123 };
        const string StringValue = "test";

        // Act
        bool result1 = additionalProperties.TryAdd(testClassValue);
        bool result2 = additionalProperties.TryAdd(anotherValue);
        bool result3 = additionalProperties.TryAdd(StringValue);

        // Assert
        Assert.True(result1);
        Assert.True(result2);
        Assert.True(result3);
        Assert.Equal(3, additionalProperties.Count);
        Assert.Same(testClassValue, additionalProperties[typeof(TestClass).FullName!]);
        Assert.Same(anotherValue, additionalProperties[typeof(AnotherTestClass).FullName!]);
        Assert.Equal(StringValue, additionalProperties[typeof(string).FullName!]);
    }

    #endregion

    #region TryGetValue Method Tests

    [Fact]
    public void TryGetValue_WithExistingValue_ReturnsTrueAndValue()
    {
        // Arrange
        AdditionalPropertiesDictionary additionalProperties = new();
        TestClass expectedValue = new() { Name = "Test" };
        additionalProperties.Add(expectedValue);

        // Act
        bool result = additionalProperties.TryGetValue(out TestClass? actualValue);

        // Assert
        Assert.True(result);
        Assert.NotNull(actualValue);
        Assert.Same(expectedValue, actualValue);
    }

    [Fact]
    public void TryGetValue_WithNonExistingValue_ReturnsFalseAndNull()
    {
        // Arrange
        AdditionalPropertiesDictionary additionalProperties = new();

        // Act
        bool result = additionalProperties.TryGetValue(out TestClass? actualValue);

        // Assert
        Assert.False(result);
        Assert.Null(actualValue);
    }

    [Fact]
    public void TryGetValue_WithNullDictionary_ThrowsArgumentNullException()
    {
        // Arrange
        AdditionalPropertiesDictionary? additionalProperties = null;

        // Act & Assert
        Assert.Throws<ArgumentNullException>(() => additionalProperties!.TryGetValue<TestClass>(out _));
    }

    [Fact]
    public void TryGetValue_WithStringValue_ReturnsCorrectValue()
    {
        // Arrange
        AdditionalPropertiesDictionary additionalProperties = new();
        const string ExpectedValue = "test string";
        additionalProperties.Add(ExpectedValue);

        // Act
        bool result = additionalProperties.TryGetValue(out string? actualValue);

        // Assert
        Assert.True(result);
        Assert.Equal(ExpectedValue, actualValue);
    }

    [Fact]
    public void TryGetValue_WithIntValue_ReturnsCorrectValue()
    {
        // Arrange
        AdditionalPropertiesDictionary additionalProperties = new();
        const int ExpectedValue = 42;
        additionalProperties.Add(ExpectedValue);

        // Act
        bool result = additionalProperties.TryGetValue(out int actualValue);

        // Assert
        Assert.True(result);
        Assert.Equal(ExpectedValue, actualValue);
    }

    [Fact]
    public void TryGetValue_WithWrongType_ReturnsFalse()
    {
        // Arrange
        AdditionalPropertiesDictionary additionalProperties = new();
        TestClass testValue = new() { Name = "Test" };
        additionalProperties.Add(testValue);

        // Act
        bool result = additionalProperties.TryGetValue(out AnotherTestClass? actualValue);

        // Assert
        Assert.False(result);
        Assert.Null(actualValue);
    }

    [Fact]
    public void TryGetValue_AfterTryAddFails_ReturnsOriginalValue()
    {
        // Arrange
        AdditionalPropertiesDictionary additionalProperties = new();
        TestClass firstValue = new() { Name = "First" };
        TestClass secondValue = new() { Name = "Second" };
        additionalProperties.Add(firstValue);
        additionalProperties.TryAdd(secondValue);

        // Act
        bool result = additionalProperties.TryGetValue(out TestClass? actualValue);

        // Assert
        Assert.Single(additionalProperties);
        Assert.True(result);
        Assert.Same(firstValue, actualValue);
    }

    #endregion

    #region Contains Method Tests

    [Fact]
    public void Contains_WithExistingType_ReturnsTrue()
    {
        // Arrange
        AdditionalPropertiesDictionary additionalProperties = new();
        TestClass value = new() { Name = "Test" };
        additionalProperties.Add(value);

        // Act
        bool result = additionalProperties.Contains<TestClass>();

        // Assert
        Assert.True(result);
    }

    [Fact]
    public void Contains_WithNonExistingType_ReturnsFalse()
    {
        // Arrange
        AdditionalPropertiesDictionary additionalProperties = new();

        // Act
        bool result = additionalProperties.Contains<TestClass>();

        // Assert
        Assert.False(result);
    }

    [Fact]
    public void Contains_WithNullDictionary_ThrowsArgumentNullException()
    {
        // Arrange
        AdditionalPropertiesDictionary? additionalProperties = null;

        // Act & Assert
        Assert.Throws<ArgumentNullException>(() => additionalProperties!.Contains<TestClass>());
    }

    [Fact]
    public void Contains_WithDifferentType_ReturnsFalse()
    {
        // Arrange
        AdditionalPropertiesDictionary additionalProperties = new();
        TestClass value = new() { Name = "Test" };
        additionalProperties.Add(value);

        // Act
        bool result = additionalProperties.Contains<AnotherTestClass>();

        // Assert
        Assert.False(result);
    }

    [Fact]
    public void Contains_AfterRemove_ReturnsFalse()
    {
        // Arrange
        AdditionalPropertiesDictionary additionalProperties = new();
        TestClass value = new() { Name = "Test" };
        additionalProperties.Add(value);
        additionalProperties.Remove<TestClass>();

        // Act
        bool result = additionalProperties.Contains<TestClass>();

        // Assert
        Assert.False(result);
    }

    #endregion

    #region Remove Method Tests

    [Fact]
    public void Remove_WithExistingType_ReturnsTrueAndRemovesValue()
    {
        // Arrange
        AdditionalPropertiesDictionary additionalProperties = new();
        TestClass value = new() { Name = "Test" };
        additionalProperties.Add(value);

        // Act
        bool result = additionalProperties.Remove<TestClass>();

        // Assert
        Assert.True(result);
        Assert.Empty(additionalProperties);
    }

    [Fact]
    public void Remove_WithNonExistingType_ReturnsFalse()
    {
        // Arrange
        AdditionalPropertiesDictionary additionalProperties = new();

        // Act
        bool result = additionalProperties.Remove<TestClass>();

        // Assert
        Assert.False(result);
    }

    [Fact]
    public void Remove_WithNullDictionary_ThrowsArgumentNullException()
    {
        // Arrange
        AdditionalPropertiesDictionary? additionalProperties = null;

        // Act & Assert
        Assert.Throws<ArgumentNullException>(() => additionalProperties!.Remove<TestClass>());
    }

    [Fact]
    public void Remove_OnlyRemovesSpecifiedType()
    {
        // Arrange
        AdditionalPropertiesDictionary additionalProperties = new();
        TestClass testValue = new() { Name = "Test" };
        AnotherTestClass anotherValue = new() { Id = 123 };
        additionalProperties.Add(testValue);
        additionalProperties.Add(anotherValue);

        // Act
        bool result = additionalProperties.Remove<TestClass>();

        // Assert
        Assert.True(result);
        Assert.Single(additionalProperties);
        Assert.False(additionalProperties.Contains<TestClass>());
        Assert.True(additionalProperties.Contains<AnotherTestClass>());
    }

    [Fact]
    public void Remove_CalledTwice_ReturnsFalseOnSecondCall()
    {
        // Arrange
        AdditionalPropertiesDictionary additionalProperties = new();
        TestClass value = new() { Name = "Test" };
        additionalProperties.Add(value);

        // Act
        bool firstResult = additionalProperties.Remove<TestClass>();
        bool secondResult = additionalProperties.Remove<TestClass>();

        // Assert
        Assert.True(firstResult);
        Assert.False(secondResult);
    }

    #endregion

    #region Test Helper Classes

    private sealed class TestClass
    {
        public string Name { get; set; } = string.Empty;
    }

    private sealed class AnotherTestClass
    {
        public int Id { get; set; }
    }

    #endregion
}
