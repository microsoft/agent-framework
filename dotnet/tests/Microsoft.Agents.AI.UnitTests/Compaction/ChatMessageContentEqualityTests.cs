// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Text;
using Microsoft.Agents.AI.Compaction;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.UnitTests.Compaction;

/// <summary>
/// Contains tests for the <see cref="ChatMessageContentEquality"/> extension methods.
/// </summary>
public class ChatMessageContentEqualityTests
{
    #region Null and reference handling

    [Fact]
    public void BothNullReturnsTrue()
    {
        ChatMessage? a = null;
        ChatMessage? b = null;

        Assert.True(a.ContentEquals(b));
    }

    [Fact]
    public void LeftNullReturnsFalse()
    {
        ChatMessage? a = null;
        ChatMessage b = new(ChatRole.User, "Hello");

        Assert.False(a.ContentEquals(b));
    }

    [Fact]
    public void RightNullReturnsFalse()
    {
        ChatMessage a = new(ChatRole.User, "Hello");
        ChatMessage? b = null;

        Assert.False(a.ContentEquals(b));
    }

    [Fact]
    public void SameReferenceReturnsTrue()
    {
        ChatMessage a = new(ChatRole.User, "Hello");

        Assert.True(a.ContentEquals(a));
    }

    #endregion

    #region MessageId shortcut

    [Fact]
    public void MatchingMessageIdReturnsTrue()
    {
        ChatMessage a = new(ChatRole.User, "Hello") { MessageId = "msg-1" };
        ChatMessage b = new(ChatRole.User, "Hello") { MessageId = "msg-1" };

        Assert.True(a.ContentEquals(b));
    }

    [Fact]
    public void MatchingMessageIdSufficientDespiteDifferentContent()
    {
        ChatMessage a = new(ChatRole.User, "Hello") { MessageId = "msg-1" };
        ChatMessage b = new(ChatRole.Assistant, "Goodbye") { MessageId = "msg-1" };

        Assert.True(a.ContentEquals(b));
    }

    [Fact]
    public void DifferentMessageIdReturnsFalse()
    {
        ChatMessage a = new(ChatRole.User, "Hello") { MessageId = "msg-1" };
        ChatMessage b = new(ChatRole.User, "Hello") { MessageId = "msg-2" };

        Assert.False(a.ContentEquals(b));
    }

    [Fact]
    public void OnlyLeftHasMessageIdFallsThroughToContentComparison()
    {
        ChatMessage a = new(ChatRole.User, "Hello") { MessageId = "msg-1" };
        ChatMessage b = new(ChatRole.User, "Hello");

        Assert.True(a.ContentEquals(b));
    }

    [Fact]
    public void OnlyRightHasMessageIdFallsThroughToContentComparison()
    {
        ChatMessage a = new(ChatRole.User, "Hello");
        ChatMessage b = new(ChatRole.User, "Hello") { MessageId = "msg-1" };

        Assert.True(a.ContentEquals(b));
    }

    #endregion

    #region Role and AuthorName

    [Fact]
    public void DifferentRoleReturnsFalse()
    {
        ChatMessage a = new(ChatRole.User, "Hello");
        ChatMessage b = new(ChatRole.Assistant, "Hello");

        Assert.False(a.ContentEquals(b));
    }

    [Fact]
    public void DifferentAuthorNameReturnsFalse()
    {
        ChatMessage a = new(ChatRole.User, "Hello") { AuthorName = "Alice" };
        ChatMessage b = new(ChatRole.User, "Hello") { AuthorName = "Bob" };

        Assert.False(a.ContentEquals(b));
    }

    [Fact]
    public void BothNullAuthorNamesAreEqual()
    {
        ChatMessage a = new(ChatRole.User, "Hello");
        ChatMessage b = new(ChatRole.User, "Hello");

        Assert.True(a.ContentEquals(b));
    }

    #endregion

    #region TextContent

    [Fact]
    public void EqualTextContentReturnsTrue()
    {
        ChatMessage a = new(ChatRole.User, "Hello world");
        ChatMessage b = new(ChatRole.User, "Hello world");

        Assert.True(a.ContentEquals(b));
    }

    [Fact]
    public void DifferentTextContentReturnsFalse()
    {
        ChatMessage a = new(ChatRole.User, "Hello");
        ChatMessage b = new(ChatRole.User, "Goodbye");

        Assert.False(a.ContentEquals(b));
    }

    [Fact]
    public void TextContentIsCaseSensitive()
    {
        ChatMessage a = new(ChatRole.User, "Hello");
        ChatMessage b = new(ChatRole.User, "hello");

        Assert.False(a.ContentEquals(b));
    }

    #endregion

    #region TextReasoningContent

    [Fact]
    public void EqualTextReasoningContentReturnsTrue()
    {
        ChatMessage a = new(ChatRole.Assistant, [new TextReasoningContent("thinking...") { ProtectedData = "opaque" }]);
        ChatMessage b = new(ChatRole.Assistant, [new TextReasoningContent("thinking...") { ProtectedData = "opaque" }]);

        Assert.True(a.ContentEquals(b));
    }

    [Fact]
    public void DifferentReasoningTextReturnsFalse()
    {
        ChatMessage a = new(ChatRole.Assistant, [new TextReasoningContent("alpha")]);
        ChatMessage b = new(ChatRole.Assistant, [new TextReasoningContent("beta")]);

        Assert.False(a.ContentEquals(b));
    }

    [Fact]
    public void DifferentProtectedDataReturnsFalse()
    {
        ChatMessage a = new(ChatRole.Assistant, [new TextReasoningContent("same") { ProtectedData = "x" }]);
        ChatMessage b = new(ChatRole.Assistant, [new TextReasoningContent("same") { ProtectedData = "y" }]);

        Assert.False(a.ContentEquals(b));
    }

    #endregion

    #region DataContent

    [Fact]
    public void EqualDataContentReturnsTrue()
    {
        byte[] data = Encoding.UTF8.GetBytes("payload");
        ChatMessage a = new(ChatRole.User, [new DataContent(data, "application/octet-stream") { Name = "file.bin" }]);
        ChatMessage b = new(ChatRole.User, [new DataContent(data, "application/octet-stream") { Name = "file.bin" }]);

        Assert.True(a.ContentEquals(b));
    }

    [Fact]
    public void DifferentDataBytesReturnsFalse()
    {
        ChatMessage a = new(ChatRole.User, [new DataContent(Encoding.UTF8.GetBytes("aaa"), "text/plain")]);
        ChatMessage b = new(ChatRole.User, [new DataContent(Encoding.UTF8.GetBytes("bbb"), "text/plain")]);

        Assert.False(a.ContentEquals(b));
    }

    [Fact]
    public void DifferentMediaTypeReturnsFalse()
    {
        byte[] data = [1, 2, 3];
        ChatMessage a = new(ChatRole.User, [new DataContent(data, "image/png")]);
        ChatMessage b = new(ChatRole.User, [new DataContent(data, "image/jpeg")]);

        Assert.False(a.ContentEquals(b));
    }

    [Fact]
    public void DifferentDataContentNameReturnsFalse()
    {
        byte[] data = [1, 2, 3];
        ChatMessage a = new(ChatRole.User, [new DataContent(data, "image/png") { Name = "a.png" }]);
        ChatMessage b = new(ChatRole.User, [new DataContent(data, "image/png") { Name = "b.png" }]);

        Assert.False(a.ContentEquals(b));
    }

    #endregion

    #region UriContent

    [Fact]
    public void EqualUriContentReturnsTrue()
    {
        ChatMessage a = new(ChatRole.User, [new UriContent(new Uri("https://example.com/image.png"), "image/png")]);
        ChatMessage b = new(ChatRole.User, [new UriContent(new Uri("https://example.com/image.png"), "image/png")]);

        Assert.True(a.ContentEquals(b));
    }

    [Fact]
    public void DifferentUriReturnsFalse()
    {
        ChatMessage a = new(ChatRole.User, [new UriContent(new Uri("https://a.com/x"), "image/png")]);
        ChatMessage b = new(ChatRole.User, [new UriContent(new Uri("https://b.com/x"), "image/png")]);

        Assert.False(a.ContentEquals(b));
    }

    [Fact]
    public void DifferentUriMediaTypeReturnsFalse()
    {
        Uri uri = new("https://example.com/file");
        ChatMessage a = new(ChatRole.User, [new UriContent(uri, "image/png")]);
        ChatMessage b = new(ChatRole.User, [new UriContent(uri, "image/jpeg")]);

        Assert.False(a.ContentEquals(b));
    }

    #endregion

    #region ErrorContent

    [Fact]
    public void EqualErrorContentReturnsTrue()
    {
        ChatMessage a = new(ChatRole.Assistant, [new ErrorContent("fail") { ErrorCode = "E001" }]);
        ChatMessage b = new(ChatRole.Assistant, [new ErrorContent("fail") { ErrorCode = "E001" }]);

        Assert.True(a.ContentEquals(b));
    }

    [Fact]
    public void DifferentErrorMessageReturnsFalse()
    {
        ChatMessage a = new(ChatRole.Assistant, [new ErrorContent("fail")]);
        ChatMessage b = new(ChatRole.Assistant, [new ErrorContent("crash")]);

        Assert.False(a.ContentEquals(b));
    }

    [Fact]
    public void DifferentErrorCodeReturnsFalse()
    {
        ChatMessage a = new(ChatRole.Assistant, [new ErrorContent("fail") { ErrorCode = "E001" }]);
        ChatMessage b = new(ChatRole.Assistant, [new ErrorContent("fail") { ErrorCode = "E002" }]);

        Assert.False(a.ContentEquals(b));
    }

    #endregion

    #region FunctionCallContent

    [Fact]
    public void EqualFunctionCallContentReturnsTrue()
    {
        ChatMessage a = new(ChatRole.Assistant, [new FunctionCallContent("call-1", "get_weather") { Arguments = new Dictionary<string, object?> { ["city"] = "Seattle" } }]);
        ChatMessage b = new(ChatRole.Assistant, [new FunctionCallContent("call-1", "get_weather") { Arguments = new Dictionary<string, object?> { ["city"] = "Seattle" } }]);

        Assert.True(a.ContentEquals(b));
    }

    [Fact]
    public void DifferentCallIdReturnsFalse()
    {
        ChatMessage a = new(ChatRole.Assistant, [new FunctionCallContent("call-1", "get_weather")]);
        ChatMessage b = new(ChatRole.Assistant, [new FunctionCallContent("call-2", "get_weather")]);

        Assert.False(a.ContentEquals(b));
    }

    [Fact]
    public void DifferentFunctionNameReturnsFalse()
    {
        ChatMessage a = new(ChatRole.Assistant, [new FunctionCallContent("call-1", "get_weather")]);
        ChatMessage b = new(ChatRole.Assistant, [new FunctionCallContent("call-1", "get_time")]);

        Assert.False(a.ContentEquals(b));
    }

    [Fact]
    public void DifferentArgumentsReturnsFalse()
    {
        ChatMessage a = new(ChatRole.Assistant, [new FunctionCallContent("call-1", "fn") { Arguments = new Dictionary<string, object?> { ["x"] = "1" } }]);
        ChatMessage b = new(ChatRole.Assistant, [new FunctionCallContent("call-1", "fn") { Arguments = new Dictionary<string, object?> { ["x"] = "2" } }]);

        Assert.False(a.ContentEquals(b));
    }

    [Fact]
    public void NullArgumentsBothSidesReturnsTrue()
    {
        ChatMessage a = new(ChatRole.Assistant, [new FunctionCallContent("call-1", "fn")]);
        ChatMessage b = new(ChatRole.Assistant, [new FunctionCallContent("call-1", "fn")]);

        Assert.True(a.ContentEquals(b));
    }

    [Fact]
    public void OneNullArgumentsReturnsFalse()
    {
        ChatMessage a = new(ChatRole.Assistant, [new FunctionCallContent("call-1", "fn")]);
        ChatMessage b = new(ChatRole.Assistant, [new FunctionCallContent("call-1", "fn") { Arguments = new Dictionary<string, object?> { ["x"] = "1" } }]);

        Assert.False(a.ContentEquals(b));
    }

    [Fact]
    public void DifferentArgumentCountReturnsFalse()
    {
        ChatMessage a = new(ChatRole.Assistant, [new FunctionCallContent("call-1", "fn") { Arguments = new Dictionary<string, object?> { ["x"] = "1" } }]);
        ChatMessage b = new(ChatRole.Assistant, [new FunctionCallContent("call-1", "fn") { Arguments = new Dictionary<string, object?> { ["x"] = "1", ["y"] = "2" } }]);

        Assert.False(a.ContentEquals(b));
    }

    #endregion

    #region FunctionResultContent

    [Fact]
    public void EqualFunctionResultContentReturnsTrue()
    {
        ChatMessage a = new(ChatRole.Tool, [new FunctionResultContent("call-1", "sunny")]);
        ChatMessage b = new(ChatRole.Tool, [new FunctionResultContent("call-1", "sunny")]);

        Assert.True(a.ContentEquals(b));
    }

    [Fact]
    public void DifferentResultCallIdReturnsFalse()
    {
        ChatMessage a = new(ChatRole.Tool, [new FunctionResultContent("call-1", "sunny")]);
        ChatMessage b = new(ChatRole.Tool, [new FunctionResultContent("call-2", "sunny")]);

        Assert.False(a.ContentEquals(b));
    }

    [Fact]
    public void DifferentResultValueReturnsFalse()
    {
        ChatMessage a = new(ChatRole.Tool, [new FunctionResultContent("call-1", "sunny")]);
        ChatMessage b = new(ChatRole.Tool, [new FunctionResultContent("call-1", "rainy")]);

        Assert.False(a.ContentEquals(b));
    }

    #endregion

    #region HostedFileContent

    [Fact]
    public void EqualHostedFileContentReturnsTrue()
    {
        ChatMessage a = new(ChatRole.User, [new HostedFileContent("file-abc") { MediaType = "text/csv", Name = "data.csv" }]);
        ChatMessage b = new(ChatRole.User, [new HostedFileContent("file-abc") { MediaType = "text/csv", Name = "data.csv" }]);

        Assert.True(a.ContentEquals(b));
    }

    [Fact]
    public void DifferentFileIdReturnsFalse()
    {
        ChatMessage a = new(ChatRole.User, [new HostedFileContent("file-abc")]);
        ChatMessage b = new(ChatRole.User, [new HostedFileContent("file-xyz")]);

        Assert.False(a.ContentEquals(b));
    }

    [Fact]
    public void DifferentHostedFileMediaTypeReturnsFalse()
    {
        ChatMessage a = new(ChatRole.User, [new HostedFileContent("file-abc") { MediaType = "text/csv" }]);
        ChatMessage b = new(ChatRole.User, [new HostedFileContent("file-abc") { MediaType = "text/plain" }]);

        Assert.False(a.ContentEquals(b));
    }

    [Fact]
    public void DifferentHostedFileNameReturnsFalse()
    {
        ChatMessage a = new(ChatRole.User, [new HostedFileContent("file-abc") { Name = "a.csv" }]);
        ChatMessage b = new(ChatRole.User, [new HostedFileContent("file-abc") { Name = "b.csv" }]);

        Assert.False(a.ContentEquals(b));
    }

    #endregion

    #region Content list structure

    [Fact]
    public void DifferentContentCountReturnsFalse()
    {
        ChatMessage a = new(ChatRole.User, [new TextContent("one"), new TextContent("two")]);
        ChatMessage b = new(ChatRole.User, [new TextContent("one")]);

        Assert.False(a.ContentEquals(b));
    }

    [Fact]
    public void MixedContentTypesInSameOrderReturnsTrue()
    {
        ChatMessage a = new(ChatRole.Assistant, new AIContent[] { new TextContent("reply"), new FunctionCallContent("c1", "fn") });
        ChatMessage b = new(ChatRole.Assistant, new AIContent[] { new TextContent("reply"), new FunctionCallContent("c1", "fn") });

        Assert.True(a.ContentEquals(b));
    }

    [Fact]
    public void MismatchedContentTypeOrderReturnsFalse()
    {
        ChatMessage a = new(ChatRole.Assistant, new AIContent[] { new TextContent("reply"), new FunctionCallContent("c1", "fn") });
        ChatMessage b = new(ChatRole.Assistant, new AIContent[] { new FunctionCallContent("c1", "fn"), new TextContent("reply") });

        Assert.False(a.ContentEquals(b));
    }

    [Fact]
    public void EmptyContentsListsAreEqual()
    {
        ChatMessage a = new() { Role = ChatRole.User, Contents = [] };
        ChatMessage b = new() { Role = ChatRole.User, Contents = [] };

        Assert.True(a.ContentEquals(b));
    }

    [Fact]
    public void SameContentItemReferenceReturnsTrue()
    {
        // Exercises the ReferenceEquals fast-path on individual AIContent items.
        TextContent shared = new("Hello");
        ChatMessage a = new(ChatRole.User, [shared]);
        ChatMessage b = new(ChatRole.User, [shared]);

        Assert.True(a.ContentEquals(b));
    }

    #endregion

    #region Unknown AIContent subtype

    [Fact]
    public void UnknownContentSubtypeSameTypeReturnsTrue()
    {
        // Unknown subtypes with the same concrete type are considered equal.
        ChatMessage a = new(ChatRole.User, [new StubContent()]);
        ChatMessage b = new(ChatRole.User, [new StubContent()]);

        Assert.True(a.ContentEquals(b));
    }

    [Fact]
    public void DifferentUnknownContentSubtypesReturnFalse()
    {
        ChatMessage a = new(ChatRole.User, [new StubContent()]);
        ChatMessage b = new(ChatRole.User, [new OtherStubContent()]);

        Assert.False(a.ContentEquals(b));
    }

    private sealed class StubContent : AIContent;

    private sealed class OtherStubContent : AIContent;

    #endregion
}
