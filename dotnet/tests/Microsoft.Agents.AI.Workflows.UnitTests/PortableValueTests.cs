// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Diagnostics.CodeAnalysis;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Workflows.Checkpointing;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Workflows.UnitTests;

public class PortableValueTests
{
    [SuppressMessage("Performance", "CA1812", Justification = "This is used as a Never/Bottom type.")]
    private sealed class Never
    {
        private Never() { }
    }

    [Theory]
    [InlineData("string")]
    [InlineData(42)]
    [InlineData(true)]
    [InlineData(3.14)]
    public async Task Test_PortableValueRoundtripAsync<T>(T value)
    {
        Assert.NotNull(value);

        PortableValue portableValue = new(value);

        Assert.False(portableValue.Is<Never>(out _));
        Assert.True(portableValue.Is(out T? returnedValue));
        Assert.Equal(value, returnedValue);
    }

    [Fact]
    public async Task Test_PortableValueRoundtripObjectAsync()
    {
        ChatMessage value = new(ChatRole.User, "Hello?");

        PortableValue portableValue = new(value);

        Assert.False(portableValue.Is<Never>(out _));
        Assert.True(portableValue.Is(out ChatMessage? returnedValue));
        Assert.Equal(value, returnedValue);
    }

    [Theory]
    [InlineData("string")]
    [InlineData(42)]
    [InlineData(true)]
    [InlineData(3.14)]
    public async Task Test_DelayedSerializationRoundtripAsync<T>(T value)
    {
        Assert.NotNull(value);

        TestDelayedDeserialization<T> delayed = new(value);
        PortableValue portableValue = new(delayed);

        Assert.False(portableValue.Is<Never>(out _));
        Assert.True(portableValue.Is(out object? obj));
        Assert.False(obj is T);
        PortableValue nestedPortableValue = Assert.IsType<PortableValue>(obj);
        Assert.Equal(value, nestedPortableValue.As<T>());

        Assert.True(portableValue.Is(out T? returnedValue));
        Assert.Equal(value, returnedValue);
    }

    [Fact]
    public async Task Test_DelayedSerializationRoundtripObjectAsync()
    {
        ChatMessage value = new(ChatRole.User, "Hello?");

        TestDelayedDeserialization<ChatMessage> delayed = new(value);
        PortableValue portableValue = new(delayed);

        Assert.False(portableValue.Is<Never>(out _));
        Assert.True(portableValue.Is(out object? obj));
        Assert.False(obj is ChatMessage);
        PortableValue nestedPortableValue = Assert.IsType<PortableValue>(obj);
        Assert.Equal(value, nestedPortableValue.As<ChatMessage>());

        Assert.True(portableValue.Is(out ChatMessage? returnedValue));
        Assert.Equal(value, returnedValue);
    }

    private sealed class TestDelayedDeserialization<T> : IDelayedDeserialization
    {
        [NotNull]
        public T Value { get; }

        public TestDelayedDeserialization([DisallowNull] T value)
        {
            this.Value = value;
        }

        public TValue Deserialize<TValue>()
        {
            if (typeof(TValue) == typeof(object))
            {
                return (TValue)(object)new PortableValue(this.Value);
            }

            if (this.Value is TValue value)
            {
                return value;
            }

            throw new InvalidOperationException();
        }

        public object? Deserialize(Type targetType)
        {
            if (targetType == typeof(object))
            {
                return new PortableValue(this.Value);
            }

            if (targetType.IsInstanceOfType(this.Value))
            {
                return this.Value;
            }

            return null;
        }
    }
}
