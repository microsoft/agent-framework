// Copyright (c) Microsoft. All rights reserved.

namespace Microsoft.Extensions.AI;

/// <summary>
/// Extension methods for <see cref="ChatOptions"/> to support new chat options.
/// </summary>
/// <remarks>
/// This class provides temporary extension methods for <see cref="ChatOptions"/> to support
/// new chat options that are not yet part of the official <see cref="ChatOptions"/> class.
/// Later, these methods should be moved to the official <see cref="ChatOptions"/> class
/// as new properties.
/// </remarks>
public static class NewChatOptionsExtensions
{
    /// <summary>
    /// Sets whether the chat client should await the run result.
    /// </summary>
    /// <remarks>
    /// This is a temporary extension method to support new chat options.
    /// It will be removed once the official <see cref="ChatOptions"/> class
    /// has been updated with the new properties. Therefore, please expect a breaking change
    /// if you are using this method directly in your code.
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
    /// This is a temporary extension method to support new chat options.
    /// It will be removed once the official <see cref="ChatOptions"/> class
    /// has been updated with the new properties. Therefore, please expect a breaking change
    /// if you are using this method directly in your code.
    /// </remarks>
    /// <param name="options">The chat options to modify.</param>
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
}
