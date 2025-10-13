// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Diagnostics.CodeAnalysis;
using System.Threading.Tasks;
using FluentAssertions;
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
        value.Should().NotBeNull();

        PortableValue portableValue = new(value);

        portableValue.Is<Never>(out _).Should().BeFalse();
        portableValue.Is(out T? returnedValue).Should().BeTrue();
        returnedValue.Should().Be(value);
    }

    [Fact]
    public async Task Test_PortableValueRoundtripObjectAsync()
    {
        ChatMessage value = new(ChatRole.User, "Hello?");

        PortableValue portableValue = new(value);

        portableValue.Is<Never>(out _).Should().BeFalse();
        portableValue.Is(out ChatMessage? returnedValue).Should().BeTrue();
        returnedValue.Should().Be(value);
    }

    [Theory]
    [InlineData("string")]
    [InlineData(42)]
    [InlineData(true)]
    [InlineData(3.14)]
    public async Task Test_DelayedSerializationRoundtripAsync<T>(T value)
    {
        value.Should().NotBeNull();

        TestDelayedDeserialization<T> delayed = new(value);
        PortableValue portableValue = new(delayed);

        portableValue.Is<Never>(out _).Should().BeFalse();
        portableValue.Is(out object? obj).Should().BeTrue();
        obj.Should().NotBeOfType<T>();
        obj.Should().BeOfType<PortableValue>()
                .And.Subject.As<PortableValue>()
                            .As<T>().Should().Be(value);

        portableValue.Is(out T? returnedValue).Should().BeTrue();
        returnedValue.Should().Be(value);
    }

    [Fact]
    public async Task Test_DelayedSerializationRoundtripObjectAsync()
    {
        ChatMessage value = new(ChatRole.User, "Hello?");

        TestDelayedDeserialization<ChatMessage> delayed = new(value);
        PortableValue portableValue = new(delayed);

        portableValue.Is<Never>(out _).Should().BeFalse();
        portableValue.Is(out object? obj).Should().BeTrue();
        obj.Should().NotBeOfType<ChatMessage>();
        obj.Should().BeOfType<PortableValue>()
                .And.Subject.As<PortableValue>()
                            .As<ChatMessage>().Should().Be(value);

        portableValue.Is(out ChatMessage? returnedValue).Should().BeTrue();
        returnedValue.Should().Be(value);
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
