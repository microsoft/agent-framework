// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json.Serialization;

namespace Microsoft.Agents.AI.FoundryMemory.Core.Models;

/// <summary>
/// Definition for a memory store specifying the models to use.
/// </summary>
internal sealed class MemoryStoreDefinitionRequest
{
    /// <summary>
    /// Gets or sets the kind of memory store definition.
    /// </summary>
    [JsonPropertyName("kind")]
    public string Kind { get; set; } = "default";

    /// <summary>
    /// Gets or sets the deployment name of the chat model for memory processing.
    /// </summary>
    [JsonPropertyName("chat_model")]
    public string? ChatModel { get; set; }

    /// <summary>
    /// Gets or sets the deployment name of the embedding model for memory search.
    /// </summary>
    [JsonPropertyName("embedding_model")]
    public string? EmbeddingModel { get; set; }
}
