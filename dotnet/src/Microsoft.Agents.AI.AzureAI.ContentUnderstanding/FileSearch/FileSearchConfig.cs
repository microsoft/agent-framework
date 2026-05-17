// Copyright (c) Microsoft. All rights reserved.

using Azure.AI.Projects;
using Microsoft.Extensions.AI;
using OpenAI;

namespace Microsoft.Agents.AI.AzureAI.ContentUnderstanding;

/// <summary>
/// Configures optional integration with a vector-store-backed <c>file_search</c> tool.
/// </summary>
/// <remarks>
/// <para>
/// When set on <see cref="ContentUnderstandingContextProviderOptions.FileSearchConfig"/>, ready
/// documents are uploaded to the configured vector store rather than injected into
/// <c>AIContext.Messages</c>, and the caller-supplied <c>file_search</c> tool is added to
/// <c>AIContext.Tools</c>.
/// </para>
/// <para>
/// Construct via the static factories <see cref="FromFoundry"/> or <see cref="FromOpenAI"/>
/// for the two built-in backends, or use the object initializer for a custom
/// <see cref="FileSearchBackend"/>.
/// </para>
/// <para>
/// Vector store creation and lifetime, plus the <c>file_search</c> tool object itself, are
/// caller-owned — <see cref="ContentUnderstandingContextProvider.DisposeAsync"/> deletes only
/// the files this provider uploaded, never the vector store.
/// </para>
/// </remarks>
public sealed class FileSearchConfig
{
    /// <summary>The backend used to perform file uploads and deletes against the vector store. Required.</summary>
    public FileSearchBackend Backend { get; init; } = default!;

    /// <summary>The id of an existing, caller-owned vector store. Required.</summary>
    public string VectorStoreId { get; init; } = default!;

    /// <summary>
    /// The caller-supplied <c>file_search</c> tool that will be added to <c>AIContext.Tools</c>
    /// when at least one document has been uploaded to <see cref="VectorStoreId"/>. Required.
    /// </summary>
    /// <remarks>
    /// The tool reference is opaque to this package; it is forwarded as-is into the LLM-facing
    /// <c>AIContext.Tools</c>. Typically this is a Responses-API <c>FileSearchTool</c>
    /// (which is currently marked experimental — <c>OPENAI001</c>).
    /// </remarks>
    public AITool FileSearchTool { get; init; } = default!;

    /// <summary>
    /// Gets or sets whether <see cref="AnalysisSection.Fields"/> data is included in the payload
    /// uploaded to the file-search vector store. Defaults to <see langword="false"/> (decision D2),
    /// because the field block is verbose and pollutes vector embeddings.
    /// </summary>
    public bool IncludeFields { get; set; }

    /// <summary>
    /// Builds a <see cref="FileSearchConfig"/> backed by a
    /// <see cref="FoundryFileSearchBackend"/>. Convenience wrapper around the object
    /// initializer for the most common Foundry case.
    /// </summary>
    /// <param name="projectClient">An authenticated Foundry project client.</param>
    /// <param name="vectorStoreId">Id of an existing, caller-owned vector store.</param>
    /// <param name="fileSearchTool">The caller-supplied <c>file_search</c> tool.</param>
    /// <param name="includeFields">Whether to include the field block in uploaded payloads. Defaults to <see langword="false"/>.</param>
    public static FileSearchConfig FromFoundry(
        AIProjectClient projectClient,
        string vectorStoreId,
        AITool fileSearchTool,
        bool includeFields = false)
    {
        _ = projectClient ?? throw new ArgumentNullException(nameof(projectClient));
        _ = vectorStoreId ?? throw new ArgumentNullException(nameof(vectorStoreId));
        _ = fileSearchTool ?? throw new ArgumentNullException(nameof(fileSearchTool));

        return new FileSearchConfig
        {
            Backend = new FoundryFileSearchBackend(projectClient),
            VectorStoreId = vectorStoreId,
            FileSearchTool = fileSearchTool,
            IncludeFields = includeFields,
        };
    }

    /// <summary>
    /// Builds a <see cref="FileSearchConfig"/> backed by an
    /// <see cref="OpenAIFileSearchBackend"/>. Convenience wrapper around the object initializer
    /// for the raw-OpenAI case.
    /// </summary>
    /// <param name="openAiClient">An authenticated OpenAI client.</param>
    /// <param name="vectorStoreId">Id of an existing, caller-owned vector store.</param>
    /// <param name="fileSearchTool">The caller-supplied <c>file_search</c> tool.</param>
    /// <param name="includeFields">Whether to include the field block in uploaded payloads. Defaults to <see langword="false"/>.</param>
    public static FileSearchConfig FromOpenAI(
        OpenAIClient openAiClient,
        string vectorStoreId,
        AITool fileSearchTool,
        bool includeFields = false)
    {
        _ = openAiClient ?? throw new ArgumentNullException(nameof(openAiClient));
        _ = vectorStoreId ?? throw new ArgumentNullException(nameof(vectorStoreId));
        _ = fileSearchTool ?? throw new ArgumentNullException(nameof(fileSearchTool));

        return new FileSearchConfig
        {
            Backend = new OpenAIFileSearchBackend(openAiClient),
            VectorStoreId = vectorStoreId,
            FileSearchTool = fileSearchTool,
            IncludeFields = includeFields,
        };
    }
}
