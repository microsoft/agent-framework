// Copyright (c) Microsoft. All rights reserved.

using System;
using Azure.AI.Projects;
using OpenAI;

namespace Microsoft.Agents.AI.AzureAI.ContentUnderstanding.UnitTests;

/// <summary>
/// Phase 11 — <see cref="FileSearchConfig"/> static factory helpers
/// (<c>FromOpenAI</c> and <c>FromFoundry</c>).
/// </summary>
public sealed class FileSearchConfigFactoryTests
{
    private static readonly FakeAITool s_fileSearchTool = new();

    [Fact]
    public void FromOpenAI_BuildsConfigWithOpenAIBackend()
    {
        OpenAIClient client = new("sk-fake-key");

        FileSearchConfig config = FileSearchConfig.FromOpenAI(client, "vs_abc", s_fileSearchTool);

        Assert.IsType<OpenAIFileSearchBackend>(config.Backend);
        Assert.Equal("vs_abc", config.VectorStoreId);
        Assert.Same(s_fileSearchTool, config.FileSearchTool);
    }

    [Fact]
    public void FromFoundry_BuildsConfigWithFoundryBackend()
    {
        AIProjectClient project = new(
            new Uri("https://contoso.services.ai.azure.com/api/projects/test"),
            new FakeTokenCredential());

        FileSearchConfig config = FileSearchConfig.FromFoundry(project, "vs_xyz", s_fileSearchTool);

        Assert.IsType<FoundryFileSearchBackend>(config.Backend);
        Assert.Equal("vs_xyz", config.VectorStoreId);
        Assert.Same(s_fileSearchTool, config.FileSearchTool);
    }

    [Fact]
    public void FromOpenAI_RejectsNullArguments()
    {
        OpenAIClient client = new("sk-fake-key");

        Assert.Throws<ArgumentNullException>(() => FileSearchConfig.FromOpenAI(null!, "vs", s_fileSearchTool));
        Assert.Throws<ArgumentNullException>(() => FileSearchConfig.FromOpenAI(client, null!, s_fileSearchTool));
        Assert.Throws<ArgumentNullException>(() => FileSearchConfig.FromOpenAI(client, "vs", null!));
    }

    [Fact]
    public void FromFoundry_RejectsNullArguments()
    {
        AIProjectClient project = new(
            new Uri("https://contoso.services.ai.azure.com/api/projects/test"),
            new FakeTokenCredential());

        Assert.Throws<ArgumentNullException>(() => FileSearchConfig.FromFoundry(null!, "vs", s_fileSearchTool));
        Assert.Throws<ArgumentNullException>(() => FileSearchConfig.FromFoundry(project, null!, s_fileSearchTool));
        Assert.Throws<ArgumentNullException>(() => FileSearchConfig.FromFoundry(project, "vs", null!));
    }

    [Fact]
    public void FromOpenAI_RejectsWhitespaceVectorStoreId()
    {
        // Whitespace (non-null) must surface as ArgumentException, distinct from the
        // ArgumentNullException thrown for a null id (xUnit Throws matches the exact type).
        OpenAIClient client = new("sk-fake-key");

        Assert.Throws<ArgumentException>(() => FileSearchConfig.FromOpenAI(client, "   ", s_fileSearchTool));
    }

    [Fact]
    public void FromFoundry_RejectsWhitespaceVectorStoreId()
    {
        AIProjectClient project = new(
            new Uri("https://contoso.services.ai.azure.com/api/projects/test"),
            new FakeTokenCredential());

        Assert.Throws<ArgumentException>(() => FileSearchConfig.FromFoundry(project, "   ", s_fileSearchTool));
    }
}
