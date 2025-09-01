// Copyright (c) Microsoft. All rights reserved.

using System.Diagnostics.CodeAnalysis;

namespace Microsoft.Extensions.AI;

/// <summary>
/// Extension methods for <see cref="ChatOptions"/> class.
/// </summary>
/// <remarks>
/// This class contains temporary extension methods to support new chat options
/// that are not part of the official <see cref="ChatOptions"/> class yet.
/// Later, these methods will be moved to the official <see cref="ChatOptions"/> class
/// as new properties and this class will be removed. Therefore, please expect a breaking change
/// if you are using this class directly in your code.
/// </remarks>
[ExcludeFromCodeCoverage]
public static class NewChatOptionsExtensions
{
    /// <summary>
    /// Sets whether the chat client should await the run result.
    /// </summary>
    /// <remarks>
    /// This is a temporary extension method that will be removed once the official
    /// <see cref="ChatOptions"/> class has been updated with the new properties.
    /// Therefore, please expect a breaking change if you are using this method directly in your code.
    /// </remarks>
    /// <param name="options">The chat options to modify.</param>
    /// <param name="awaitRunResult">The value indicating whether to await the run result.</param>
    public static void SetAwaitRunResult(this ChatOptions options, bool awaitRunResult)
    {
        (options.AdditionalProperties ??= [])["AwaitRunResult"] = awaitRunResult;
    }

    /// <summary>
    /// Gets whether the chat client should await the run result.
    /// </summary>
    /// <remarks>
    /// This is a temporary extension method that will be removed once the official
    /// <see cref="ChatOptions"/> class has been updated with the new properties.
    /// Therefore, please expect a breaking change if you are using this method directly in your code.
    /// </remarks>
    /// <param name="options">The chat options.</param>
    /// <returns>A value indicating whether to await the run result.</returns>
    public static bool? GetAwaitRunResult(this ChatOptions options)
    {
        if (options.AdditionalProperties is { } additionalProperties &&
            additionalProperties.TryGetValue("AwaitRunResult", out object? value) &&
            value is bool awaitRunResult)
        {
            return awaitRunResult;
        }

        return null;
    }

    /// <summary>
    /// Sets the identifier of an update within a conversation to start generating chat responses after.
    /// </summary>
    /// <remarks>
    /// This is a temporary extension method that will be removed once the official
    /// <see cref="ChatOptions"/> class has been updated with the new properties.
    /// Therefore, please expect a breaking change if you are using this method directly in your code.
    /// </remarks>
    /// <param name="options">The chat options to modify.</param>
    /// <param name="startAfter">The identifier of the update to start generating responses after.</param>
    public static void SetStartAfter(this ChatOptions options, string startAfter)
    {
        (options.AdditionalProperties ??= [])["StartAfter"] = startAfter;
    }

    /// <summary>
    /// Gets the identifier of an update within a conversation to start generating chat responses after.
    /// </summary>
    /// <remarks>
    /// This is a temporary extension method that will be removed once the official
    /// <see cref="ChatOptions"/> class has been updated with the new properties.
    /// Therefore, please expect a breaking change if you are using this method directly in your code.
    /// </remarks>
    /// <param name="options">The chat options.</param>
    /// <returns>>The identifier of the update to start generating responses after, or <c>null</c> if not set.</returns>
    public static string? GetStartAfter(this ChatOptions options)
    {
        if (options.AdditionalProperties is { } additionalProperties &&
            additionalProperties.TryGetValue("StartAfter", out object? value) &&
            value is string startAfter)
        {
            return startAfter;
        }

        return null;
    }

    /// <summary>
    /// Sets the identifier of the previous response in a conversation.
    /// </summary>
    /// <remarks>
    /// This is a temporary extension method that will be removed once the official
    /// <see cref="ChatOptions"/> class has been updated with the new properties.
    /// Therefore, please expect a breaking change if you are using this method directly in your code.
    /// </remarks>
    /// <param name="options">The chat options to modify.</param>
    /// <param name="previousResponseId">The identifier of the previous response.</param>
    public static void SetPreviousResponseId(this ChatOptions options, string previousResponseId)
    {
        (options.AdditionalProperties ??= [])["PreviousResponseId"] = previousResponseId;
    }

    /// <summary>
    /// Gets the identifier of the previous response in a conversation.
    /// </summary>
    /// <remarks>
    /// This is a temporary extension method that will be removed once the official
    /// <see cref="ChatOptions"/> class has been updated with the new properties.
    /// Therefore, please expect a breaking change if you are using this method directly in your code.
    /// </remarks>
    /// <param name="options">The chat options.</param>
    /// <returns>The identifier of the previous response, or <c>null</c> if not set.</returns>
    public static string? GetPreviousResponseId(this ChatOptions options)
    {
        if (options.AdditionalProperties is { } additionalProperties &&
            additionalProperties.TryGetValue("PreviousResponseId", out object? value) &&
            value is string previousResponseId)
        {
            return previousResponseId;
        }

        return null;
    }
}
