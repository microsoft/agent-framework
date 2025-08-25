// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Diagnostics.CodeAnalysis;

namespace Microsoft.Extensions.AI;

/// <summary>
/// Provides extension methods for the <see cref="ChatResponse"/> class.
/// </summary>
/// <remarks>
/// This class contains temporary extension methods to support new chat response properties
/// that are not part of the official <see cref="ChatResponse"/> class yet.
/// Later, these methods will be moved to the official <see cref="ChatResponse"/> class
/// as new properties and this class will be removed. Therefore, please expect a breaking change
/// if you are using this class directly in your code.
/// </remarks>
[ExcludeFromCodeCoverage]
public static class NewChatResponseExtensions
{
    /// <summary>
    /// Sets the status of the specified <see cref="ChatResponse"/> to the provided value.
    /// </summary>
    /// <remarks>
    /// This is a temporary extension method that will be removed once the official
    /// <see cref="ChatResponse"/> class has been updated with the new properties.
    /// Therefore, please expect a breaking change if you are using this method directly in your code.
    /// </remarks>
    /// <param name="response">The <see cref="ChatResponse"/> instance whose status is to be updated.</param>
    /// <param name="status">The new status to assign.</param>
    public static void SetResponseStatus(this ChatResponse response, NewResponseStatus? status)
    {
        if (response is null)
        {
            throw new ArgumentNullException(nameof(response));
        }

        (response.AdditionalProperties ??= [])["Status"] = status;
    }

    /// <summary>
    /// Gets the status of the specified <see cref="ChatResponse"/>.
    /// </summary>
    /// <remarks>
    /// This is a temporary extension method that will be removed once the official
    /// <see cref="ChatResponse"/> class has been updated with the new properties.
    /// Therefore, please expect a breaking change if you are using this method directly in your code.
    /// </remarks>
    /// <param name="response">The <see cref="ChatResponse"/> instance from which to retrieve the status.</param>
    /// <returns>The <see cref="NewResponseStatus"/> if it exists; otherwise, <c>null</c>.</returns>
    public static NewResponseStatus? GetResponseStatus(this ChatResponse response)
    {
        if (response is null)
        {
            throw new ArgumentNullException(nameof(response));
        }

        if (response.AdditionalProperties is not null &&
            response.AdditionalProperties.TryGetValue("Status", out var value) &&
            value is NewResponseStatus status)
        {
            return status;
        }

        return null;
    }
}
