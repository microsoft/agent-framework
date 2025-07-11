// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.Orchestration.UnitTest;

public class DefaultTransformsTests
{
    [Fact]
    public async Task FromInputAsyncWithEnumerableOfChatMessageReturnsInputAsync()
    {
        // Arrange
        IEnumerable<ChatMessage> input =
        [
            new(ChatRole.User, "Hello"),
            new(ChatRole.Assistant, "Hi there")
        ];

        // Act
        IEnumerable<ChatMessage> result = await DefaultTransforms.FromInput(input);

        // Assert
        Assert.Equal(input, result);
    }

    [Fact]
    public async Task FromInputAsyncWithChatMessageReturnsInputAsListAsync()
    {
        // Arrange
        ChatMessage input = new(ChatRole.User, "Hello");

        // Act
        IEnumerable<ChatMessage> result = await DefaultTransforms.FromInput(input);

        // Assert
        Assert.Single(result);
        Assert.Equal(input, result.First());
    }

    [Fact]
    public async Task FromInputAsyncWithStringInputReturnsUserChatMessageAsync()
    {
        // Arrange
        string input = "Hello, world!";

        // Act
        IEnumerable<ChatMessage> result = await DefaultTransforms.FromInput(input);

        // Assert
        Assert.Single(result);
        ChatMessage message = result.First();
        Assert.Equal(ChatRole.User, message.Role);
        Assert.Equal(input, message.Text);
    }

    [Fact]
    public async Task FromInputAsyncWithObjectInputSerializesAsJsonAsync()
    {
        // Arrange
        TestObject input = new() { Id = 1, Name = "Test" };

        // Act
        IEnumerable<ChatMessage> result = await DefaultTransforms.FromInput(input);

        // Assert
        Assert.Single(result);
        ChatMessage message = result.First();
        Assert.Equal(ChatRole.User, message.Role);

        string expectedJson = JsonSerializer.Serialize(input);
        Assert.Equal(expectedJson, message.Text);
    }

    [Fact]
    public async Task ToOutputAsyncWithOutputTypeMatchingInputListReturnsSameListAsync()
    {
        // Arrange
        IList<ChatMessage> input =
        [
            new(ChatRole.User, "Hello"),
            new(ChatRole.Assistant, "Hi there")
        ];

        // Act
        IList<ChatMessage> result = await DefaultTransforms.ToOutput<IList<ChatMessage>>(input);

        // Assert
        Assert.Same(input, result);
    }

    [Fact]
    public async Task ToOutputAsyncWithOutputTypeChatMessageReturnsSingleMessageAsync()
    {
        // Arrange
        IList<ChatMessage> input =
        [
            new(ChatRole.User, "Hello")
        ];

        // Act
        ChatMessage result = await DefaultTransforms.ToOutput<ChatMessage>(input);

        // Assert
        Assert.Same(input[0], result);
    }

    [Fact]
    public async Task ToOutputAsyncWithOutputTypeStringReturnsContentOfSingleMessageAsync()
    {
        // Arrange
        string expected = "Hello, world!";
        IList<ChatMessage> input =
        [
            new(ChatRole.User, expected)
        ];

        // Act
        string result = await DefaultTransforms.ToOutput<string>(input);

        // Assert
        Assert.Equal(expected, result);
    }

    [Fact]
    public async Task ToOutputAsyncWithOutputTypeDeserializableDeserializesFromContentAsync()
    {
        // Arrange
        TestObject expected = new() { Id = 42, Name = "TestName" };
        string json = JsonSerializer.Serialize(expected);
        IList<ChatMessage> input =
        [
            new(ChatRole.User, json)
        ];

        // Act
        TestObject result = await DefaultTransforms.ToOutput<TestObject>(input);

        // Assert
        Assert.Equal(expected.Id, result.Id);
        Assert.Equal(expected.Name, result.Name);
    }

    [Fact]
    public async Task ToOutputAsyncWithInvalidJsonThrowsExceptionAsync()
    {
        // Arrange
        IList<ChatMessage> input =
        [
            new(ChatRole.User, "Not valid JSON")
        ];

        // Act & Assert
        await Assert.ThrowsAsync<InvalidOperationException>(async () =>
            await DefaultTransforms.ToOutput<TestObject>(input)
        );
    }

    [Fact]
    public async Task ToOutputAsyncWithMultipleMessagesAndNonMatchingTypeThrowsExceptionAsync()
    {
        // Arrange
        IList<ChatMessage> input =
        [
            new(ChatRole.User, "Hello"),
            new(ChatRole.Assistant, "Hi there")
        ];

        // Act & Assert
        await Assert.ThrowsAsync<InvalidOperationException>(async () =>
            await DefaultTransforms.ToOutput<TestObject>(input)
        );
    }

    [Fact]
    public async Task ToOutputAsyncWithNullContentHandlesGracefullyAsync()
    {
        // Arrange
        IList<ChatMessage> input =
        [
            new(ChatRole.User, (string?)null)
        ];

        // Act
        string result = await DefaultTransforms.ToOutput<string>(input);

        // Assert
        Assert.Equal(string.Empty, result);
    }

    private sealed class TestObject
    {
        public int Id { get; set; }
        public string? Name { get; set; }
    }
}
