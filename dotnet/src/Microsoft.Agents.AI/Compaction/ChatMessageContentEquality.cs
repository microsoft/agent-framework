// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Compaction;

/// <summary>
/// Content-based equality comparison for <see cref="ChatMessage"/> instances.
/// </summary>
internal static class ChatMessageContentEquality
{
    /// <summary>
    /// Determines whether two <see cref="ChatMessage"/> instances represent the same message by content.
    /// </summary>
    /// <remarks>
    /// When both messages define a <see cref="ChatMessage.MessageId"/>, identity is determined solely
    /// by that identifier.  Otherwise, the comparison falls through to <see cref="ChatMessage.Role"/>,
    /// <see cref="ChatMessage.AuthorName"/>, and each item in <see cref="ChatMessage.Contents"/>.
    /// </remarks>
    internal static bool ContentEquals(this ChatMessage? message, ChatMessage? other)
    {
        if (ReferenceEquals(message, other))
        {
            return true;
        }

        if (message is null || other is null)
        {
            return false;
        }

        // A matching MessageId is sufficient.
        if (message.MessageId is not null && other.MessageId is not null)
        {
            return string.Equals(message.MessageId, other.MessageId, StringComparison.Ordinal);
        }

        if (message.Role != other.Role)
        {
            return false;
        }

        if (!string.Equals(message.AuthorName, other.AuthorName, StringComparison.Ordinal))
        {
            return false;
        }

        return ContentsEqual(message.Contents, other.Contents);
    }

    private static bool ContentsEqual(IList<AIContent> left, IList<AIContent> right)
    {
        if (left.Count != right.Count)
        {
            return false;
        }

        for (int i = 0; i < left.Count; i++)
        {
            if (!ContentItemEquals(left[i], right[i]))
            {
                return false;
            }
        }

        return true;
    }

    private static bool ContentItemEquals(AIContent left, AIContent right)
    {
        if (ReferenceEquals(left, right))
        {
            return true;
        }

        if (left.GetType() != right.GetType())
        {
            return false;
        }

        return (left, right) switch
        {
            (TextContent a, TextContent b) => TextContentEquals(a, b),
            (TextReasoningContent a, TextReasoningContent b) => TextReasoningContentEquals(a, b),
            (DataContent a, DataContent b) => DataContentEquals(a, b),
            (UriContent a, UriContent b) => UriContentEquals(a, b),
            (ErrorContent a, ErrorContent b) => ErrorContentEquals(a, b),
            (FunctionCallContent a, FunctionCallContent b) => FunctionCallContentEquals(a, b),
            (FunctionResultContent a, FunctionResultContent b) => FunctionResultContentEquals(a, b),
            (HostedFileContent a, HostedFileContent b) => HostedFileContentEquals(a, b),
            (AIContent a, AIContent b) => a.GetType() == b.GetType(),
        };
    }

    private static bool TextContentEquals(TextContent a, TextContent b) =>
        string.Equals(a.Text, b.Text, StringComparison.Ordinal);

    private static bool TextReasoningContentEquals(TextReasoningContent a, TextReasoningContent b) =>
        string.Equals(a.Text, b.Text, StringComparison.Ordinal) &&
        string.Equals(a.ProtectedData, b.ProtectedData, StringComparison.Ordinal);

    private static bool DataContentEquals(DataContent a, DataContent b) =>
        string.Equals(a.MediaType, b.MediaType, StringComparison.Ordinal) &&
        string.Equals(a.Name, b.Name, StringComparison.Ordinal) &&
        a.Data.Span.SequenceEqual(b.Data.Span);

    private static bool UriContentEquals(UriContent a, UriContent b) =>
        Equals(a.Uri, b.Uri) &&
        string.Equals(a.MediaType, b.MediaType, StringComparison.Ordinal);

    private static bool ErrorContentEquals(ErrorContent a, ErrorContent b) =>
        string.Equals(a.Message, b.Message, StringComparison.Ordinal) &&
        string.Equals(a.ErrorCode, b.ErrorCode, StringComparison.Ordinal) &&
        Equals(a.Details, b.Details);

    private static bool FunctionCallContentEquals(FunctionCallContent a, FunctionCallContent b) =>
        string.Equals(a.CallId, b.CallId, StringComparison.Ordinal) &&
        string.Equals(a.Name, b.Name, StringComparison.Ordinal) &&
        ArgumentsEqual(a.Arguments, b.Arguments);

    private static bool FunctionResultContentEquals(FunctionResultContent a, FunctionResultContent b) =>
        string.Equals(a.CallId, b.CallId, StringComparison.Ordinal) &&
        Equals(a.Result, b.Result);

    private static bool ArgumentsEqual(IDictionary<string, object?>? left, IDictionary<string, object?>? right)
    {
        if (ReferenceEquals(left, right))
        {
            return true;
        }

        if (left is null || right is null)
        {
            return false;
        }

        if (left.Count != right.Count)
        {
            return false;
        }

        foreach (KeyValuePair<string, object?> entry in left)
        {
            if (!right.TryGetValue(entry.Key, out object? value) || !Equals(entry.Value, value))
            {
                return false;
            }
        }

        return true;
    }

    private static bool HostedFileContentEquals(HostedFileContent a, HostedFileContent b) =>
        string.Equals(a.FileId, b.FileId, StringComparison.Ordinal) &&
        string.Equals(a.MediaType, b.MediaType, StringComparison.Ordinal) &&
        string.Equals(a.Name, b.Name, StringComparison.Ordinal);
}
