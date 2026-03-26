// Copyright (c) Microsoft. All rights reserved.

using System;
using System.ClientModel;
using System.ClientModel.Primitives;
using System.IO;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Azure.AI.Projects;

namespace Microsoft.Agents.AI.FoundryMemory;

/// <summary>
/// Internal extension methods for <see cref="AIProjectClient"/> to provide MemoryStores helper operations.
/// </summary>
internal static class AIProjectClientExtensions
{
    private static readonly ModelReaderWriterOptions s_wireOptions = new("W");

    /// <summary>
    /// Creates a memory store if it doesn't already exist.
    /// </summary>
    internal static async Task<bool> CreateMemoryStoreIfNotExistsAsync(
        this AIProjectClient client,
        string memoryStoreName,
        string? description,
        string chatModel,
        string embeddingModel,
        CancellationToken cancellationToken)
    {
        try
        {
            await client.MemoryStores.GetMemoryStoreAsync(memoryStoreName, cancellationToken.ToRequestOptions()).ConfigureAwait(false);
            return false; // Store already exists
        }
        catch (ClientResultException ex) when (ex.Status == 404)
        {
            // Store doesn't exist, create it
        }

        MemoryStoreDefaultDefinition definition = new(chatModel, embeddingModel);
        BinaryContent content = CreateMemoryStoreContent(memoryStoreName, definition, description);
        await client.MemoryStores.CreateMemoryStoreAsync(content, cancellationToken.ToRequestOptions()).ConfigureAwait(false);
        return true;
    }

    private static BinaryContent CreateMemoryStoreContent(string name, MemoryStoreDefaultDefinition definition, string? description)
    {
        using MemoryStream stream = new();
        using (Utf8JsonWriter writer = new(stream))
        {
            writer.WriteStartObject();
            writer.WriteString("name", name);

            writer.WritePropertyName("definition");
            using (JsonDocument defDoc = JsonDocument.Parse(ModelReaderWriter.Write(definition, s_wireOptions, AzureAIProjectsContext.Default)))
            {
                defDoc.RootElement.WriteTo(writer);
            }

            if (description is not null)
            {
                writer.WriteString("description", description);
            }

            writer.WriteEndObject();
        }

        return BinaryContent.Create(BinaryData.FromBytes(stream.ToArray()));
    }
}
