// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json.Nodes;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.AgentHooks.UnitTests;

public class AgentHooksCodecTests
{
    [Fact]
    public void WireEqualityDistinguishesBoolFromNumber()
    {
        // Assert
        Assert.False(Wire.WireEquals(JsonValue.Create(true), JsonValue.Create(1)));
        Assert.False(Wire.WireEquals(JsonValue.Create(false), JsonValue.Create(0)));
        Assert.True(Wire.WireEquals(JsonValue.Create(1), JsonValue.Create(1)));
    }

    [Fact]
    public void InputCodecMapsRolesOntoTheSpecEnum()
    {
        // Arrange / Act / Assert: user and system pass through; anything else is external.
        Assert.Equal("user", Wire.InputRole(ChatRole.User));
        Assert.Equal("system", Wire.InputRole(ChatRole.System));
        Assert.Equal("external", Wire.InputRole(ChatRole.Assistant));
        Assert.Equal("external", Wire.InputRole(ChatRole.Tool));
    }

    [Fact]
    public void ToolArgumentsCodecMergesOnlyChangedKeys()
    {
        // Arrange: a non-JSON-native original value that a faithful projection cannot
        // round-trip; the transform touches a different key.
        var opaque = new byte[] { 1, 2, 3 };
        var arguments = new AIFunctionArguments { ["location"] = "Paris", ["blob"] = opaque };
        var before = ToolArgumentsCodec.ToWire(arguments);
        var after = (JsonObject)before.DeepClone();
        after["location"] = "Berlin";

        // Act
        _ = ToolArgumentsCodec.WriteBack(arguments, before, after, out var merged);

        // Assert: only the changed key was taken from the wire; the untouched key keeps
        // its original native value by identity.
        Assert.NotNull(merged);
        Assert.Equal("Berlin", (merged!["location"] as JsonNode)?.GetValue<string>());
        Assert.Same(opaque, merged["blob"]);
    }

    [Fact]
    public void ToolArgumentsCodecUntouchedTargetIsANoOp()
    {
        // Arrange
        var arguments = new AIFunctionArguments { ["location"] = "Paris" };
        var before = ToolArgumentsCodec.ToWire(arguments);

        // Act
        _ = ToolArgumentsCodec.WriteBack(arguments, before, before.DeepClone(), out var merged);

        // Assert
        Assert.Null(merged);
    }

    [Fact]
    public void ToolArgumentsCodecNonObjectTransformFailsClosed()
    {
        // Arrange
        var arguments = new AIFunctionArguments { ["location"] = "Paris" };
        var before = ToolArgumentsCodec.ToWire(arguments);

        // Act / Assert
        _ = Assert.Throws<AgentHooksWriteBackException>(
            () => ToolArgumentsCodec.WriteBack(arguments, before, JsonValue.Create("nope"), out _));
    }

    [Fact]
    public void MessageListWriteBackMatchesByIdentityNotPosition()
    {
        // Arrange: three originals; the transform removes the middle one.
        List<ChatMessage> originals =
        [
            new ChatMessage(ChatRole.User, "first"),
            new ChatMessage(ChatRole.User, "second"),
            new ChatMessage(ChatRole.User, "third"),
        ];
        List<JsonObject> before = [.. originals.Select(Wire.MessageToWire)];
        var after = new JsonArray(before[0].DeepClone(), before[2].DeepClone());

        // Act
        var result = Wire.WriteBackMessageList(originals, before, after, "test");

        // Assert: removal did not shift content onto the wrong original.
        Assert.Equal(2, result.Count);
        Assert.Same(originals[0], result[0]);
        Assert.Same(originals[2], result[1]);
        Assert.Equal("third", result[1].Text);
    }

    [Fact]
    public void ModelResponseCodecSurfacesHostedToolCallsInContent()
    {
        // Arrange: one host-executed call and one service-executed (informational) call.
        var hostCall = new FunctionCallContent("call-1", "local_tool", new Dictionary<string, object?>());
        var hostedCall = new FunctionCallContent("call-2", "hosted_tool", new Dictionary<string, object?>())
        {
            InformationalOnly = true,
        };
        var response = new ChatResponse(new ChatMessage(ChatRole.Assistant, [hostCall, hostedCall]));

        // Act
        var wire = ModelResponseCodec.ToWire(response);

        // Assert: the host-executed call rides tool_calls; the hosted call is part of
        // the response content, where it stays interceptable.
        var calls = Assert.IsType<JsonArray>(wire["tool_calls"]);
        Assert.Single(calls);
        Assert.Equal("local_tool", calls[0]?["name"]?.GetValue<string>());
        Assert.Contains("hosted_tool", wire["content"]?.ToJsonString(), StringComparison.Ordinal);
    }

    [Theory]
    [InlineData("""[{"id":"","name":"tool","args":{}}]""")] // empty id
    [InlineData("""[{"id":1,"name":"tool","args":{}}]""")] // non-string id
    [InlineData("""[{"name":"tool","args":{}}]""")] // missing id
    [InlineData("""[{"id":"c1","name":"","args":{}}]""")] // empty name
    [InlineData("""[{"id":"c1","args":{}}]""")] // missing name
    [InlineData("""[{"id":"c1","name":"tool"}]""")] // missing args
    [InlineData("""[{"id":"c1","name":"tool","args":"nope"}]""")] // non-object args
    [InlineData("""[{"id":"c1","name":"a","args":{}},{"id":"c1","name":"b","args":{}}]""")] // duplicate ids
    public void ToolCallTransformValidationFailsClosedOnMalformedShapes(string toolCallsJson)
    {
        // Arrange: a transform that adds/reshapes tool calls with an invalid shape must
        // fail closed instead of producing malformed native calls.
        var response = new ChatResponse(new ChatMessage(ChatRole.Assistant, "text"));
        var before = ModelResponseCodec.ToWire(response);
        var after = (JsonObject)before.DeepClone();
        after["tool_calls"] = JsonNode.Parse(toolCallsJson);

        // Act / Assert
        _ = Assert.Throws<AgentHooksWriteBackException>(() => ModelResponseCodec.WriteBack(response, before, after));
    }

    [Fact]
    public void MessageListWriteBackDefaultsMissingRoleToUserMatchingPython()
    {
        // Arrange: the merged Python codec defaults a missing per-message role to "user"
        // in message-list write-backs (str(item.get("role") or "user")); this port
        // mirrors that documented behavior exactly.
        List<ChatMessage> originals = [new ChatMessage(ChatRole.User, "original")];
        List<JsonObject> before = [.. originals.Select(Wire.MessageToWire)];
        var after = new JsonArray(new JsonObject { ["content"] = "rewritten" });

        // Act
        var result = Wire.WriteBackMessageList(originals, before, after, "test");

        // Assert: the role-less entry adopted the user default, so the original user
        // message was mutated in place rather than replaced.
        Assert.Same(originals[0], Assert.Single(result));
        Assert.Equal("rewritten", result[0].Text);
        Assert.Equal(ChatRole.User, result[0].Role);
    }

    [Fact]
    public void ResponseContentWriteBackDefaultsMissingRoleToAssistantMatchingPython()
    {
        // Arrange: the merged Python response codec defaults a missing role to
        // "assistant" (str(wire_message.get("role") or "assistant")); mirrored here.
        var response = new ChatResponse(new ChatMessage(ChatRole.Assistant, "original"));
        var before = ModelResponseCodec.ToWire(response);
        var after = (JsonObject)before.DeepClone();
        after["content"] = new JsonArray(new JsonObject { ["content"] = "rewritten" });

        // Act
        _ = ModelResponseCodec.WriteBack(response, before, after);

        // Assert
        var message = Assert.Single(response.Messages);
        Assert.Equal(ChatRole.Assistant, message.Role);
        Assert.Equal("rewritten", message.Text);
    }

    [Fact]
    public void ToolResultCodecUntouchedTargetKeepsOriginalIdentity()
    {
        // Arrange
        var original = new Dictionary<string, object?> { ["value"] = 42 };
        var wire = ToolResultCodec.ToWire(original);

        // Act
        var result = ToolResultCodec.WriteBack(original, wire, wire?.DeepClone());

        // Assert
        Assert.Same(original, result);
    }

    [Fact]
    public void ToolResultCodecPreservesTextContentWrappers()
    {
        // Arrange: the canonical single-text-content result shape.
        List<AIContent> original = [new TextContent("raw")];
        var wire = ToolResultCodec.ToWire(original);

        // Act
        var result = ToolResultCodec.WriteBack(original, wire, JsonValue.Create("clean"));

        // Assert
        var contents = Assert.IsType<List<AIContent>>(result);
        Assert.Equal("clean", Assert.IsType<TextContent>(contents[0]).Text);
    }

    [Fact]
    public void OutputCodecUntouchedTargetIsANoOp()
    {
        // Arrange
        var message = new ChatMessage(ChatRole.Assistant, "answer");
        var response = new AgentResponse(message);
        var before = OutputCodec.ToWire(response);

        // Act
        bool changed = OutputCodec.WriteBack(response, before, new JsonObject { ["content"] = before?.DeepClone() });

        // Assert
        Assert.False(changed);
        Assert.Same(message, response.Messages.Single());
    }

    [Fact]
    public void OutputCodecUnsupportedTransformFailsClosed()
    {
        // Arrange
        var response = new AgentResponse(new ChatMessage(ChatRole.Assistant, "answer"));
        var before = OutputCodec.ToWire(response);

        // Act / Assert: a non-object output target cannot be written back.
        _ = Assert.Throws<AgentHooksWriteBackException>(
            () => OutputCodec.WriteBack(response, before, JsonValue.Create(42)));
    }

    [Fact]
    public void WireToContentsDecodesRichContentAndFailsClosedOnGarbage()
    {
        // Arrange
        var text = Wire.WireToContents(JsonValue.Create("plain"), "test");

        // Assert: strings decode as text content.
        Assert.Equal("plain", Assert.IsType<TextContent>(Assert.Single(text)).Text);

        // Assert: a round-tripped rich content object decodes back to its type.
        var image = new DataContent(new byte[] { 1, 2, 3 }, "image/png");
        var projected = Wire.ContentsToWire([new TextContent("t"), image]);
        var decoded = Wire.WireToContents(projected, "test");
        Assert.Equal(2, decoded.Count);
        _ = Assert.IsType<DataContent>(decoded[1]);

        // Assert: an unsupported item fails closed instead of being dropped.
        _ = Assert.Throws<AgentHooksWriteBackException>(
            () => Wire.WireToContents(new JsonArray(new JsonObject { ["no_type"] = "x" }), "test"));
    }
}
