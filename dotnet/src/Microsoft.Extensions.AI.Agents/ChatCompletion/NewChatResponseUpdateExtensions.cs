// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Diagnostics.CodeAnalysis;

namespace Microsoft.Extensions.AI;

/// <summary>
/// Provides extension methods for the <see cref="ChatResponseUpdate"/> class.
/// </summary>
/// <remarks>
/// This class contains temporary extension methods to support new chat response properties
/// that are not part of the official <see cref="ChatResponseUpdate"/> class yet.
/// Later, these methods will be moved to the official <see cref="ChatResponseUpdate"/> class
/// as new properties and this class will be removed. Therefore, please expect a breaking change
/// if you are using this class directly in your code.
/// </remarks>
[ExcludeFromCodeCoverage]
public static class NewChatResponseUpdateExtensions
{
    /// <summary>
    /// Sets the status of the specified <see cref="ChatResponseUpdate"/> to the provided value.
    /// </summary>
    /// <remarks>
    /// This is a temporary extension method that will be removed once the official
    /// <see cref="ChatResponseUpdate"/> class has been updated with the new properties.
    /// Therefore, please expect a breaking change if you are using this method directly in your code.
    /// </remarks>
    /// <param name="update">The <see cref="ChatResponseUpdate"/> instance whose status is to be updated.</param>
    /// <param name="status">The new status to assign.</param>
    public static void SetResponseStatus(this ChatResponseUpdate update, NewResponseStatus? status)
    {
        if (status is not null)
        {
            (update.AdditionalProperties ??= [])["Status"] = status;
        }
    }

    /// <summary>
    /// Gets the status of the specified <see cref="ChatResponseUpdate"/>.
    /// </summary>
    /// <remarks>
    /// This is a temporary extension method that will be removed once the official
    /// <see cref="ChatResponseUpdate"/> class has been updated with the new properties.
    /// Therefore, please expect a breaking change if you are using this method directly in your code.
    /// </remarks>
    /// <param name="update">The <see cref="ChatResponseUpdate"/> instance from which to retrieve the status.</param>
    /// <returns>The <see cref="NewResponseStatus"/> if it exists; otherwise, <c>null</c>.</returns>
    public static NewResponseStatus? GetResponseStatus(this ChatResponseUpdate update)
    {
        if (update is null)
        {
            throw new ArgumentNullException(nameof(update));
        }

        if (update.AdditionalProperties is not null &&
            update.AdditionalProperties.TryGetValue("Status", out var value) &&
            value is NewResponseStatus status)
        {
            return status;
        }

        return null;
    }

    /// <summary>
    /// Sets the sequence number of an update within a conversation.
    /// </summary>
    /// <remarks>
    /// This is a temporary extension method that will be removed once the official
    /// <see cref="ChatResponseUpdate"/> class has been updated with the new properties.
    /// Therefore, please expect a breaking change if you are using this method directly in your code.
    /// </remarks>
    /// <param name="update">The <see cref="ChatResponseUpdate"/> instance to modify.</param>
    /// <param name="sequenceNumber">The sequence number to set.</param>
    public static void SetSequenceNumber(this ChatResponseUpdate update, int? sequenceNumber)
    {
        if (update is null)
        {
            throw new ArgumentNullException(nameof(update));
        }

        (update.AdditionalProperties ??= [])["SequenceNumber"] = sequenceNumber;
    }

    /// <summary>
    /// Gets the sequence number of an update within a conversation.
    /// </summary>
    /// <remarks>
    /// This is a temporary extension method that will be removed once the official
    /// <see cref="ChatResponseUpdate"/> class has been updated with the new properties.
    /// Therefore, please expect a breaking change if you are using this method directly in your code.
    /// </remarks>
    /// <param name="update">The <see cref="ChatResponseUpdate"/> instance to read from.</param>
    /// <returns>The sequence number if it exists; otherwise, <c>null</c>.</returns>
    public static int? GetSequenceNumber(this ChatResponseUpdate update)
    {
        if (update is null)
        {
            throw new ArgumentNullException(nameof(update));
        }

        if (update.AdditionalProperties is not null &&
            update.AdditionalProperties.TryGetValue("SequenceNumber", out var value) &&
            value is int sequenceNumber)
        {
            return sequenceNumber;
        }

        return null;
    }
}
