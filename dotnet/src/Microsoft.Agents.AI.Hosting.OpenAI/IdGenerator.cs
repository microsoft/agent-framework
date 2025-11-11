// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Security.Cryptography;
using System.Text.RegularExpressions;
using Microsoft.Agents.AI.Hosting.OpenAI.Responses.Models;

namespace Microsoft.Agents.AI.Hosting.OpenAI;

/// <summary>
/// Generates IDs with partition keys.
/// </summary>
internal sealed partial class IdGenerator
{
    private readonly string _partitionId;
    private readonly Random? _random;

#if NET9_0_OR_GREATER
    [GeneratedRegex("^[A-Za-z0-9]+$")]
    private static partial Regex WatermarkRegex();
#else
    private static readonly Regex s_watermarkRegex = new("^[A-Za-z0-9]+$", RegexOptions.Compiled);
    private static Regex WatermarkRegex() => s_watermarkRegex;
#endif

    /// <summary>
    /// Initializes a new instance of the <see cref="IdGenerator"/> class.
    /// </summary>
    /// <param name="responseId">The response ID.</param>
    /// <param name="conversationId">The conversation ID.</param>
    /// <param name="randomSeed">Optional random seed for deterministic ID generation. When null, uses cryptographically secure random generation.</param>
    public IdGenerator(string? responseId, string? conversationId, int? randomSeed = null)
    {
        this._random = randomSeed.HasValue ? new Random(randomSeed.Value) : null;
        this.ResponseId = responseId ?? NewId("resp", random: this._random);
        this.ConversationId = conversationId ?? NewId("conv", random: this._random);
        this._partitionId = GetPartitionIdOrDefault(this.ConversationId) ?? string.Empty;
    }

    /// <summary>
    /// Creates a new ID generator from a create response request.
    /// </summary>
    /// <param name="request">The create response request.</param>
    /// <returns>A new ID generator.</returns>
    public static IdGenerator From(CreateResponse request)
    {
        string? responseId = null;
        request.Metadata?.TryGetValue("response_id", out responseId);
        return new IdGenerator(responseId, request.Conversation?.Id);
    }

    /// <summary>
    /// Gets the response ID.
    /// </summary>
    public string ResponseId { get; }

    /// <summary>
    /// Gets the conversation ID.
    /// </summary>
    public string ConversationId { get; }

    /// <summary>
    /// Generates a new ID.
    /// </summary>
    /// <param name="category">The optional category for the ID.</param>
    /// <returns>A generated ID string.</returns>
    public string Generate(string? category = null)
    {
        var prefix = string.IsNullOrEmpty(category) ? "id" : category;
        return NewId(prefix, partitionKey: this._partitionId, random: this._random);
    }

    /// <summary>
    /// Generates a function call ID.
    /// </summary>
    /// <returns>A function call ID.</returns>
    public string GenerateFunctionCallId() => this.Generate("func");

    /// <summary>
    /// Generates a function output ID.
    /// </summary>
    /// <returns>A function output ID.</returns>
    public string GenerateFunctionOutputId() => this.Generate("funcout");

    /// <summary>
    /// Generates a message ID.
    /// </summary>
    /// <returns>A message ID.</returns>
    public string GenerateMessageId() => this.Generate("msg");

    /// <summary>
    /// Generates a reasoning ID.
    /// </summary>
    /// <returns>A reasoning ID.</returns>
    public string GenerateReasoningId() => this.Generate("rs");

    /// <summary>
    /// Generates a new ID with a structured format that includes a partition key.
    /// </summary>
    /// <param name="prefix">The prefix to add to the ID, typically indicating the resource type.</param>
    /// <param name="stringLength">The length of the random entropy string in the ID.</param>
    /// <param name="partitionKeyLength">The length of the partition key if generating a new one.</param>
    /// <param name="infix">Optional additional text to insert between the prefix and the entropy.</param>
    /// <param name="watermark">Optional text to insert in the middle of the entropy string for traceability.</param>
    /// <param name="delimiter">The delimiter character used to separate parts of the ID.</param>
    /// <param name="partitionKey">An explicit partition key to use. When provided, this value will be used instead of generating a new one.</param>
    /// <param name="partitionKeyHint">An existing ID to extract the partition key from. When provided, the same partition key will be used instead of generating a new one.</param>
    /// <param name="random">The random number generator.</param>
    /// <returns>A new ID with format "{prefix}{delimiter}{infix}{entropy}{delimiter}{partitionKey}".</returns>
    /// <exception cref="ArgumentException">Thrown when the watermark contains non-alphanumeric characters.</exception>
    public static string NewId(string prefix, int stringLength = 32, int partitionKeyLength = 16, string infix = "",
        string watermark = "", string delimiter = "_", string? partitionKey = null, string partitionKeyHint = "",
        Random? random = null)
    {
        ArgumentOutOfRangeException.ThrowIfLessThan(stringLength, 1);
        var entropy = GetRandomString(stringLength, random);

        string pKey = partitionKey ?? GetPartitionIdOrDefault(partitionKeyHint) ?? GetRandomString(partitionKeyLength, random);

        if (!string.IsNullOrEmpty(watermark))
        {
            if (!WatermarkRegex().IsMatch(watermark))
            {
                throw new ArgumentException($"Only alphanumeric characters may be in watermark: {watermark}",
                    nameof(watermark));
            }

            entropy = $"{entropy[..(stringLength / 2)]}{watermark}{entropy[(stringLength / 2)..]}";
        }

        infix ??= "";
        prefix = !string.IsNullOrEmpty(prefix) ? $"{prefix}{delimiter}" : "";
        return $"{prefix}{infix}{entropy}{pKey}";
    }

    /// <summary>
    /// Generates a secure random alphanumeric string of the specified length.
    /// When a random seed was provided to the constructor, uses deterministic generation.
    /// </summary>
    /// <param name="stringLength">The desired length of the random string.</param>
    /// <param name="random">The optional random number generator.</param>
    /// <returns>A random alphanumeric string.</returns>
    /// <exception cref="ArgumentException">Thrown when stringLength is less than 1.</exception>
    private static string GetRandomString(int stringLength, Random? random)
    {
        const string Chars = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789";
        if (random is not null)
        {
            // Use deterministic random generation when seed is provided
            return string.Create(stringLength, random, static (destination, random) =>
            {
                for (int i = 0; i < destination.Length; i++)
                {
                    destination[i] = Chars[random.Next(Chars.Length)];
                }
            });
        }

        // Use cryptographically secure random generation when no seed is provided
        return RandomNumberGenerator.GetString(Chars, stringLength);
    }

    /// <summary>
    /// Extracts the partition key from an existing ID, or returns null if extraction fails.
    /// </summary>
    /// <param name="id">The ID to extract the partition key from.</param>
    /// <param name="stringLength">The length of the random entropy string in the ID.</param>
    /// <param name="partitionKeyLength">The length of the partition key if generating a new one.</param>
    /// <param name="delimiter">The delimiter character used in the ID.</param>
    /// <returns>The partition key if successfully extracted; otherwise, null.</returns>
    private static string? GetPartitionIdOrDefault(string? id, int stringLength = 32, int partitionKeyLength = 16,
        string delimiter = "_")
    {
        if (string.IsNullOrEmpty(id))
        {
            return null;
        }

        var parts = id.Split([delimiter], StringSplitOptions.RemoveEmptyEntries);
        if (parts.Length < 2)
        {
            return null;
        }

        if (parts[1].Length < stringLength + partitionKeyLength)
        {
            return null;
        }

        // get last partitionKeyLength characters from the last part as the partition key
        return parts[1][^partitionKeyLength..];
    }
}
