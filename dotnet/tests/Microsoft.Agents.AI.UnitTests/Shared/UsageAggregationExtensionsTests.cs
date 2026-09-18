// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Reflection;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.UnitTests;

/// <summary>
/// Unit tests for <see cref="UsageAggregationExtensions"/>.
/// </summary>
public class UsageAggregationExtensionsTests
{
    /// <summary>
    /// Aggregated usage is reported by updating the response in place rather than by copying it, so that a
    /// derived response type returned by an inner client survives. Only <see cref="ChatResponse.Usage"/> is
    /// touched; every other property is left exactly as the inner client set it.
    /// </summary>
    [Fact]
    public void ApplyAggregatedUsage_ChatResponse_UpdatesInPlaceAndLeavesEveryOtherPropertyUntouched()
    {
        // Arrange
        ChatMessage message = new(ChatRole.Assistant, "hello");
        ChatResponse original = new([message])
        {
            ResponseId = "resp-1",
            ConversationId = "conv-1",
            ModelId = "model-1",
            CreatedAt = new DateTimeOffset(2024, 1, 2, 3, 4, 5, TimeSpan.Zero),
            FinishReason = ChatFinishReason.Stop,
            Usage = CreateUsage(1, 1, 2),
            ContinuationToken = new TestContinuationToken(),
            RawRepresentation = new object(),
            AdditionalProperties = new() { ["key"] = "value" },
        };

        PropertySnapshot before = PropertySnapshot.Capture(original);
        UsageDetails aggregated = CreateUsage(10, 20, 30);

        // Act
        ChatResponse result = original.ApplyAggregatedUsage(aggregated);

        // Assert
        Assert.Same(original, result);
        Assert.Same(aggregated, result.Usage);
        Assert.Equal([message], result.Messages);
        before.AssertUnchangedExceptUsage(result);
    }

    /// <summary>
    /// The <see cref="AgentResponse"/> overload behaves identically: the inner agent's response instance is
    /// updated in place so that its runtime type and any state it carries survive.
    /// </summary>
    [Fact]
    public void ApplyAggregatedUsage_AgentResponse_UpdatesInPlaceAndLeavesEveryOtherPropertyUntouched()
    {
        // Arrange
        ChatMessage message = new(ChatRole.Assistant, "hello");
        AgentResponse original = new([message])
        {
            AgentId = "agent-1",
            ResponseId = "resp-1",
            CreatedAt = new DateTimeOffset(2024, 1, 2, 3, 4, 5, TimeSpan.Zero),
            FinishReason = ChatFinishReason.Stop,
            Usage = CreateUsage(1, 1, 2),
            ContinuationToken = new TestContinuationToken(),
            RawRepresentation = new object(),
            AdditionalProperties = new() { ["key"] = "value" },
        };

        PropertySnapshot before = PropertySnapshot.Capture(original);
        UsageDetails aggregated = CreateUsage(10, 20, 30);

        // Act
        AgentResponse result = original.ApplyAggregatedUsage(aggregated);

        // Assert
        Assert.Same(original, result);
        Assert.Same(aggregated, result.Usage);
        Assert.Equal([message], result.Messages);
        before.AssertUnchangedExceptUsage(result);
    }

    /// <summary>
    /// When a run returns a transcript spanning multiple invocations, the supplied messages replace those of
    /// the final response while every other property is left as the inner agent set it.
    /// </summary>
    [Fact]
    public void ApplyAggregatedUsage_AgentResponse_SubstitutesSuppliedMessagesAndRetainsMetadata()
    {
        // Arrange
        AgentResponse original = new([new ChatMessage(ChatRole.Assistant, "last")])
        {
            AgentId = "agent-1",
            RawRepresentation = new object(),
        };
        object rawRepresentation = original.RawRepresentation;

        List<ChatMessage> transcript =
        [
            new(ChatRole.Assistant, "first"),
            new(ChatRole.Assistant, "last"),
        ];

        // Act
        AgentResponse result = original.ApplyAggregatedUsage(null, transcript);

        // Assert
        Assert.Same(original, result);
        Assert.Same(transcript, result.Messages);
        Assert.Equal("agent-1", result.AgentId);
        Assert.Same(rawRepresentation, result.RawRepresentation);
        Assert.Null(result.Usage);
    }

    /// <summary>
    /// Omitting the messages argument must leave the response's existing messages alone, since most callers
    /// only need to correct the reported usage.
    /// </summary>
    [Fact]
    public void ApplyAggregatedUsage_NoMessagesSupplied_LeavesMessagesUntouched()
    {
        // Arrange
        List<ChatMessage> messages = [new(ChatRole.Assistant, "hi")];
        ChatResponse chatResponse = new(messages);
        AgentResponse agentResponse = new(messages);

        // Act
        ChatResponse chatResult = chatResponse.ApplyAggregatedUsage(CreateUsage(1, 2, 3));
        AgentResponse agentResult = agentResponse.ApplyAggregatedUsage(CreateUsage(1, 2, 3));

        // Assert
        Assert.Same(messages, chatResult.Messages);
        Assert.Same(messages, agentResult.Messages);
    }

    /// <summary>
    /// A derived <see cref="ChatResponse"/> returned by an inner chat client must survive usage aggregation
    /// with its additional state intact. Building a replacement base response would silently downgrade it.
    /// </summary>
    [Fact]
    public void ApplyAggregatedUsage_DerivedChatResponse_PreservesRuntimeTypeAndDerivedState()
    {
        // Arrange
        TestDerivedChatResponse original = new([new ChatMessage(ChatRole.Assistant, "hi")]) { DerivedState = "custom" };

        // Act
        ChatResponse result = original.ApplyAggregatedUsage(CreateUsage(1, 2, 3), [new ChatMessage(ChatRole.Assistant, "transcript")]);

        // Assert
        TestDerivedChatResponse derived = Assert.IsType<TestDerivedChatResponse>(result);
        Assert.Same(original, derived);
        Assert.Equal("custom", derived.DerivedState);
        Assert.Equal(1, derived.Usage!.InputTokenCount);
    }

    /// <summary>
    /// A derived <see cref="AgentResponse"/> such as <c>AgentResponse&lt;T&gt;</c> must likewise survive usage
    /// aggregation, since replacing it with a base response would discard its deserialized result.
    /// </summary>
    [Fact]
    public void ApplyAggregatedUsage_DerivedAgentResponse_PreservesRuntimeTypeAndDerivedState()
    {
        // Arrange
        TestDerivedAgentResponse original = new([new ChatMessage(ChatRole.Assistant, "hi")]) { DerivedState = "custom" };

        // Act
        AgentResponse result = original.ApplyAggregatedUsage(CreateUsage(1, 2, 3), [new ChatMessage(ChatRole.Assistant, "transcript")]);

        // Assert
        TestDerivedAgentResponse derived = Assert.IsType<TestDerivedAgentResponse>(result);
        Assert.Same(original, derived);
        Assert.Equal("custom", derived.DerivedState);
        Assert.Equal(1, derived.Usage!.InputTokenCount);
    }

    private sealed class TestContinuationToken : ResponseContinuationToken
    {
        public override ReadOnlyMemory<byte> ToBytes() => new([1, 2, 3]);
    }

    /// <summary>
    /// Captures every settable property except <see cref="AgentResponse.Usage"/> and
    /// <see cref="AgentResponse.Messages"/>, so that a helper which starts writing to any of them is caught.
    /// </summary>
    private sealed class PropertySnapshot(Dictionary<PropertyInfo, object?> values)
    {
        public static PropertySnapshot Capture<T>(T response)
            where T : notnull
            => new(GetProperties<T>().ToDictionary(static p => p, p => p.GetValue(response)));

        public void AssertUnchangedExceptUsage<T>(T response)
            where T : notnull
        {
            Assert.NotEmpty(values);
            foreach (var entry in values)
            {
                Assert.NotNull(entry.Value);
                Assert.Equal(entry.Value, entry.Key.GetValue(response));
            }
        }

        private static IEnumerable<PropertyInfo> GetProperties<T>()
            => typeof(T)
                .GetProperties(BindingFlags.Public | BindingFlags.Instance)
                .Where(static p => p.CanWrite && p.Name is not (nameof(AgentResponse.Usage) or nameof(AgentResponse.Messages)));
    }

    private static UsageDetails CreateUsage(long? input, long? output, long? total)
        => new()
        {
            InputTokenCount = input,
            OutputTokenCount = output,
            TotalTokenCount = total,
        };
}
