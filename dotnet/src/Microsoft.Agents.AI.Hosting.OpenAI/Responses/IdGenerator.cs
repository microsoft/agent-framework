// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.AI.Hosting.OpenAI.Responses.Models;

namespace Microsoft.Agents.AI.Hosting.OpenAI.Responses;

/// <summary>
/// Generates IDs with partition keys.
/// </summary>
internal sealed partial class IdGenerator
{
    private readonly string _partitionId;

    /// <summary>
    /// Initializes a new instance of the <see cref="IdGenerator"/> class.
    /// </summary>
    /// <param name="responseId">The response ID.</param>
    /// <param name="conversationId">The conversation ID.</param>
    public IdGenerator(string? responseId, string? conversationId)
    {
        this.ResponseId = responseId ?? IdGeneratorHelpers.NewId("resp");
        this.ConversationId = conversationId ?? IdGeneratorHelpers.NewId("conv");
        this._partitionId = IdGeneratorHelpers.GetPartitionIdOrDefault(this.ConversationId) ?? string.Empty;
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
        return IdGeneratorHelpers.NewId(prefix, partitionKey: this._partitionId);
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
}
