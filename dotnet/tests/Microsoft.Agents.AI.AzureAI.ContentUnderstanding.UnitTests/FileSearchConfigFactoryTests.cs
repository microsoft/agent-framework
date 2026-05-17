// Copyright (c) Microsoft. All rights reserved.

using System;
using Azure.AI.Projects;
using Microsoft.Extensions.AI;
using OpenAI;

namespace Microsoft.Agents.AI.AzureAI.ContentUnderstanding.UnitTests;

/// <summary>
/// Phase 11 — <see cref="FileSearchConfig"/> static factory parity with Python's
/// <c>FileSearchConfig.from_openai</c> / <c>from_foundry</c>.
/// </summary>
public sealed class FileSearchConfigFactoryTests
{
    private static readonly FakeAITool s_fileSearchTool = new();

    // parity: python tests/cu/test_models.py::TestFileSearchConfig::test_from_openai_factory
    [Fact]
    public void FromOpenAI_BuildsConfigWithOpenAIBackend_AndDefaultIncludeFieldsFalse()
    {
        OpenAIClient client = new("sk-fake-key");

        FileSearchConfig config = FileSearchConfig.FromOpenAI(client, "vs_abc", s_fileSearchTool);

        Assert.IsType<OpenAIFileSearchBackend>(config.Backend);
        Assert.Equal("vs_abc", config.VectorStoreId);
        Assert.Same(s_fileSearchTool, config.FileSearchTool);
        Assert.False(config.IncludeFields);
    }

    // parity: python tests/cu/test_models.py::TestFileSearchConfig::test_from_openai_factory_with_include_fields
    [Fact]
    public void FromOpenAI_PropagatesIncludeFieldsTrue()
    {
        OpenAIClient client = new("sk-fake-key");

        FileSearchConfig config = FileSearchConfig.FromOpenAI(client, "vs_abc", s_fileSearchTool, includeFields: true);

        Assert.IsType<OpenAIFileSearchBackend>(config.Backend);
        Assert.True(config.IncludeFields);
    }

    // parity: N/A — .NET-specific Foundry factory; Python only ships from_openai.
    [Fact]
    public void FromFoundry_BuildsConfigWithFoundryBackend_AndDefaultIncludeFieldsFalse()
    {
        AIProjectClient project = new(
            new Uri("https://contoso.services.ai.azure.com/api/projects/test"),
            new FakeTokenCredential());

        FileSearchConfig config = FileSearchConfig.FromFoundry(project, "vs_xyz", s_fileSearchTool);

        Assert.IsType<FoundryFileSearchBackend>(config.Backend);
        Assert.Equal("vs_xyz", config.VectorStoreId);
        Assert.Same(s_fileSearchTool, config.FileSearchTool);
        Assert.False(config.IncludeFields);
    }

    // parity: N/A — .NET-specific Foundry factory option.
    [Fact]
    public void FromFoundry_PropagatesIncludeFieldsTrue()
    {
        AIProjectClient project = new(
            new Uri("https://contoso.services.ai.azure.com/api/projects/test"),
            new FakeTokenCredential());

        FileSearchConfig config = FileSearchConfig.FromFoundry(project, "vs_xyz", s_fileSearchTool, includeFields: true);

        Assert.True(config.IncludeFields);
    }

    // parity: N/A — .NET-only defensive guards on factory parameters.
    [Fact]
    public void FromOpenAI_RejectsNullArguments()
    {
        OpenAIClient client = new("sk-fake-key");

        Assert.Throws<ArgumentNullException>(() => FileSearchConfig.FromOpenAI(null!, "vs", s_fileSearchTool));
        Assert.Throws<ArgumentNullException>(() => FileSearchConfig.FromOpenAI(client, null!, s_fileSearchTool));
        Assert.Throws<ArgumentNullException>(() => FileSearchConfig.FromOpenAI(client, "vs", null!));
    }

    // parity: N/A — .NET-only defensive guards on factory parameters.
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
}
