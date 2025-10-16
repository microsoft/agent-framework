using System;
using System.Linq;
using System.Security.Cryptography;
using System.Text.RegularExpressions;

using AzureAIAgents.Models;

namespace Azure.AI.AgentsHosting.Ingress.Common.Id;

/// <summary>
/// Generates Foundry-style IDs with partition keys.
/// </summary>
public partial class FoundryIdGenerator : IIdGenerator
{
    private readonly string _partitionId;

#if NET9_0_OR_GREATER
    [GeneratedRegex("^[A-Za-z0-9]*$")]
    private static partial Regex WatermarkRegex();
#else
    private static readonly Regex s_watermarkRegex = new("^[A-Za-z0-9]*$", RegexOptions.Compiled);
    private static Regex WatermarkRegex() => s_watermarkRegex;
#endif

    /// <summary>
    /// Initializes a new instance of the <see cref="FoundryIdGenerator"/> class.
    /// </summary>
    /// <param name="responseId">The response ID.</param>
    /// <param name="conversationId">The conversation ID.</param>
    public FoundryIdGenerator(string? responseId, string? conversationId)
    {
        this.ResponseId = responseId ?? NewId("resp");
        this.ConversationId = conversationId ?? NewId("conv");
        this._partitionId = ExtractPartitionId(this.ConversationId);
    }

    /// <summary>
    /// Creates a new ID generator from a create response request.
    /// </summary>
    /// <param name="request">The create response request.</param>
    /// <returns>A new ID generator.</returns>
    public static FoundryIdGenerator From(CreateResponse request)
    {
        request.Metadata.TryGetValue("response_id", out var responseId);
        return new FoundryIdGenerator(responseId, request.Conversation?.Id);
    }

    /// <summary>
    /// Gets the response ID.
    /// </summary>
    public string ResponseId { get; }

    /// <summary>
    /// Gets the conversation ID.
    /// </summary>
    public string ConversationId { get; }

    /// <inheritdoc/>
    public string Generate(string? category = null)
    {
        var prefix = string.IsNullOrEmpty(category) ? "id" : category;
        return NewId(prefix, partitionKey: this._partitionId);
    }

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
    /// <returns>A new ID with format "{prefix}{delimiter}{infix}{entropy}{delimiter}{partitionKey}".</returns>
    /// <exception cref="ArgumentException">Thrown when the watermark contains non-alphanumeric characters.</exception>
    private static string NewId(string prefix, int stringLength = 32, int partitionKeyLength = 16, string infix = "",
        string watermark = "", string delimiter = "_", string? partitionKey = null, string partitionKeyHint = "")
    {
        var entropy = SecureEntropy(stringLength);
        var pKey = partitionKey ?? (string.IsNullOrEmpty(partitionKeyHint)
            ? SecureEntropy(partitionKeyLength)
            : ExtractPartitionId(partitionKeyHint));

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
    /// </summary>
    /// <param name="stringLength">The desired length of the random string.</param>
    /// <returns>A random alphanumeric string.</returns>
    /// <exception cref="ArgumentException">Thrown when stringLength is less than 1.</exception>
    private static string SecureEntropy(int stringLength)
    {
        if (stringLength < 1)
        {
            throw new ArgumentException("Must greater than or equal to 1", nameof(stringLength));
        }

        var entropy = "";
        while (entropy.Length != stringLength)
        {
            var buffer = RandomNumberGenerator.GetBytes(stringLength);
            var entropyBase64 = Convert.ToBase64String(buffer);
            entropy = new string(entropyBase64.Where(char.IsLetterOrDigit).ToArray())[..stringLength];
        }

        return entropy;
    }

    /// <summary>
    /// Extracts the partition key from an existing ID.
    /// </summary>
    /// <param name="id">The ID to extract the partition key from.</param>
    /// <param name="stringLength">The length of the random entropy string in the ID.</param>
    /// <param name="partitionKeyLength">The length of the partition key if generating a new one.</param>
    /// <param name="delimiter">The delimiter character used in the ID.</param>
    /// <returns>The partition key portion of the ID.</returns>
    /// <exception cref="ArgumentException">Thrown when the ID is null, empty, or does not contain a valid partition key.</exception>
    private static string ExtractPartitionId(string id, int stringLength = 32, int partitionKeyLength = 16,
        string delimiter = "_")
    {
        if (string.IsNullOrEmpty(id))
        {
            throw new ArgumentException("Id cannot be null or empty", nameof(id));
        }

        var parts = id.Split([delimiter], StringSplitOptions.RemoveEmptyEntries);
        if (parts.Length < 2)
        {
            throw new ArgumentException($"Id '{id}' does not contain a valid partition key.", nameof(id));
        }

        if (parts[1].Length < stringLength + partitionKeyLength)
        {
            throw new ArgumentException($"Id '{id}' does not contain a valid id.", nameof(id));
        }

        // get last partitionKeyLength characters from the last part as the partition key
        return parts[1][^partitionKeyLength..];
    }
}
