// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using Moq;

namespace Microsoft.Agents.AI.UnitTests.Harness.FileAccess;

public class FileAccessProviderTests
{
    #region Constructor Validation

    [Fact]
    public void Constructor_NullFileStore_Throws()
    {
        Assert.Throws<ArgumentNullException>(() => new FileAccessProvider(null!));
    }

    [Fact]
    public void Constructor_WithDefaults_Succeeds()
    {
        // Act
        var provider = new FileAccessProvider(new InMemoryAgentFileStore());

        // Assert
        Assert.NotNull(provider);
    }

    #endregion

    #region ProvideAIContextAsync Tests

    [Fact]
    public async Task ProvideAIContextAsync_ReturnsToolsAsync()
    {
        // Arrange
        var tools = await CreateToolsAsync();

        // Assert — 5 tools: SaveFile, ReadFile, DeleteFile, ListFiles, SearchFiles
        Assert.Equal(5, tools.Count());
    }

    [Fact]
    public async Task ProvideAIContextAsync_ReturnsInstructionsAsync()
    {
        // Arrange
        var provider = new FileAccessProvider(new InMemoryAgentFileStore());
        var agent = new Mock<AIAgent>().Object;
        var session = new ChatClientAgentSession();
#pragma warning disable MAAI001
        var context = new AIContextProvider.InvokingContext(agent, session, new AIContext());
#pragma warning restore MAAI001

        // Act
        AIContext result = await provider.InvokingAsync(context);

        // Assert
        Assert.NotNull(result.Instructions);
        Assert.Contains("File Access", result.Instructions);
        Assert.Contains("FileAccess_", result.Instructions);
        Assert.Contains("persist beyond the current session", result.Instructions);
    }

    [Fact]
    public async Task ProvideAIContextAsync_DoesNotInjectMessagesAsync()
    {
        // Arrange — FileAccessProvider should never inject messages (unlike FileMemoryProvider).
        var store = new InMemoryAgentFileStore();
        await store.WriteFileAsync("notes.md", "Content");
        var provider = new FileAccessProvider(store);
        var agent = new Mock<AIAgent>().Object;
        var session = new ChatClientAgentSession();
#pragma warning disable MAAI001
        var context = new AIContextProvider.InvokingContext(agent, session, new AIContext());
#pragma warning restore MAAI001

        // Act
        AIContext result = await provider.InvokingAsync(context);

        // Assert
        Assert.Null(result.Messages);
    }

    [Fact]
    public void StateKeys_ReturnsEmpty()
    {
        // Arrange — FileAccessProvider has no session state.
        var provider = new FileAccessProvider(new InMemoryAgentFileStore());

        // Act
        var keys = provider.StateKeys;

        // Assert
        Assert.Empty(keys);
    }

    #endregion

    #region SaveFile Tests

    [Fact]
    public async Task SaveFile_CreatesFileAsync()
    {
        // Arrange
        var store = new InMemoryAgentFileStore();
        var tools = await CreateToolsAsync(store);
        var saveFile = GetTool(tools, "FileAccess_SaveFile");

        // Act
        await InvokeToolAsync(saveFile, new AIFunctionArguments
        {
            ["fileName"] = "notes.md",
            ["content"] = "Test content",
        });

        // Assert
        var content = await store.ReadFileAsync("notes.md");
        Assert.Equal("Test content", content);
    }

    [Fact]
    public async Task SaveFile_DoesNotCreateDescriptionSidecarAsync()
    {
        // Arrange — FileAccessProvider should never create description sidecar files.
        var store = new InMemoryAgentFileStore();
        var tools = await CreateToolsAsync(store);
        var saveFile = GetTool(tools, "FileAccess_SaveFile");

        // Act
        await InvokeToolAsync(saveFile, new AIFunctionArguments
        {
            ["fileName"] = "research.md",
            ["content"] = "Long research content...",
        });

        // Assert — file exists, no description sidecar
        Assert.Equal("Long research content...", await store.ReadFileAsync("research.md"));
        Assert.Null(await store.ReadFileAsync("research_description.md"));
    }

    [Fact]
    public async Task SaveFile_ExistingFile_WithoutOverwrite_ReturnsErrorAsync()
    {
        // Arrange
        var store = new InMemoryAgentFileStore();
        var tools = await CreateToolsAsync(store);
        var saveFile = GetTool(tools, "FileAccess_SaveFile");

        await InvokeToolAsync(saveFile, new AIFunctionArguments
        {
            ["fileName"] = "notes.md",
            ["content"] = "Original",
        });

        // Act — try to save again without overwrite
        var result = await InvokeToolAsync(saveFile, new AIFunctionArguments
        {
            ["fileName"] = "notes.md",
            ["content"] = "Updated",
        });

        // Assert — original content preserved, error message returned
        Assert.Equal("Original", await store.ReadFileAsync("notes.md"));
        var text = Assert.IsType<JsonElement>(result).GetString();
        Assert.Contains("already exists", text);
    }

    [Fact]
    public async Task SaveFile_ExistingFile_WithOverwrite_SucceedsAsync()
    {
        // Arrange
        var store = new InMemoryAgentFileStore();
        var tools = await CreateToolsAsync(store);
        var saveFile = GetTool(tools, "FileAccess_SaveFile");

        await InvokeToolAsync(saveFile, new AIFunctionArguments
        {
            ["fileName"] = "notes.md",
            ["content"] = "Original",
        });

        // Act — save again with overwrite=true
        await InvokeToolAsync(saveFile, new AIFunctionArguments
        {
            ["fileName"] = "notes.md",
            ["content"] = "Updated",
            ["overwrite"] = true,
        });

        // Assert
        Assert.Equal("Updated", await store.ReadFileAsync("notes.md"));
    }

    [Fact]
    public async Task SaveFile_ReturnsConfirmationAsync()
    {
        // Arrange
        var tools = await CreateToolsAsync();
        var saveFile = GetTool(tools, "FileAccess_SaveFile");

        // Act
        var result = await InvokeToolAsync(saveFile, new AIFunctionArguments
        {
            ["fileName"] = "test.md",
            ["content"] = "Content",
        });

        // Assert
        var text = Assert.IsType<JsonElement>(result).GetString();
        Assert.Contains("saved", text);
    }

    #endregion

    #region ReadFile Tests

    [Fact]
    public async Task ReadFile_ExistingFile_ReturnsContentAsync()
    {
        // Arrange
        var store = new InMemoryAgentFileStore();
        await store.WriteFileAsync("notes.md", "Stored content");
        var tools = await CreateToolsAsync(store);
        var readFile = GetTool(tools, "FileAccess_ReadFile");

        // Act
        var result = await InvokeToolAsync(readFile, new AIFunctionArguments
        {
            ["fileName"] = "notes.md",
        });

        // Assert
        var text = Assert.IsType<JsonElement>(result).GetString();
        Assert.Equal("Stored content", text);
    }

    [Fact]
    public async Task ReadFile_NonExistent_ReturnsNotFoundMessageAsync()
    {
        // Arrange
        var tools = await CreateToolsAsync();
        var readFile = GetTool(tools, "FileAccess_ReadFile");

        // Act
        var result = await InvokeToolAsync(readFile, new AIFunctionArguments
        {
            ["fileName"] = "nonexistent.md",
        });

        // Assert
        var text = Assert.IsType<JsonElement>(result).GetString();
        Assert.Contains("not found", text);
    }

    #endregion

    #region DeleteFile Tests

    [Fact]
    public async Task DeleteFile_ExistingFile_DeletesAndReturnsConfirmationAsync()
    {
        // Arrange
        var store = new InMemoryAgentFileStore();
        await store.WriteFileAsync("notes.md", "Content");
        var tools = await CreateToolsAsync(store);
        var deleteFile = GetTool(tools, "FileAccess_DeleteFile");

        // Act
        var result = await InvokeToolAsync(deleteFile, new AIFunctionArguments
        {
            ["fileName"] = "notes.md",
        });

        // Assert
        var text = Assert.IsType<JsonElement>(result).GetString();
        Assert.Contains("deleted", text);
        Assert.False(await store.FileExistsAsync("notes.md"));
    }

    [Fact]
    public async Task DeleteFile_NonExistent_ReturnsNotFoundAsync()
    {
        // Arrange
        var tools = await CreateToolsAsync();
        var deleteFile = GetTool(tools, "FileAccess_DeleteFile");

        // Act
        var result = await InvokeToolAsync(deleteFile, new AIFunctionArguments
        {
            ["fileName"] = "missing.md",
        });

        // Assert
        var text = Assert.IsType<JsonElement>(result).GetString();
        Assert.Contains("not found", text);
    }

    #endregion

    #region ListFiles Tests

    [Fact]
    public async Task ListFiles_ReturnsFileNamesAsync()
    {
        // Arrange
        var store = new InMemoryAgentFileStore();
        await store.WriteFileAsync("notes.md", "Content");
        await store.WriteFileAsync("data.txt", "Data");
        var tools = await CreateToolsAsync(store);
        var listFiles = GetTool(tools, "FileAccess_ListFiles");

        // Act
        var result = await InvokeToolAsync(listFiles, new AIFunctionArguments());

        // Assert — returns plain list of file names (no description properties)
        var entries = Assert.IsType<JsonElement>(result).EnumerateArray().ToList();
        Assert.Equal(2, entries.Count);
        Assert.Contains(entries, e => e.GetString() == "data.txt");
        Assert.Contains(entries, e => e.GetString() == "notes.md");
    }

    [Fact]
    public async Task ListFiles_DoesNotFilterDescriptionFilesAsync()
    {
        // Arrange — FileAccessProvider doesn't know about description sidecars, so all files are visible.
        var store = new InMemoryAgentFileStore();
        await store.WriteFileAsync("notes.md", "Content");
        await store.WriteFileAsync("notes_description.md", "Description");
        var tools = await CreateToolsAsync(store);
        var listFiles = GetTool(tools, "FileAccess_ListFiles");

        // Act
        var result = await InvokeToolAsync(listFiles, new AIFunctionArguments());

        // Assert — both files should be visible
        var entries = Assert.IsType<JsonElement>(result).EnumerateArray().ToList();
        Assert.Equal(2, entries.Count);
    }

    [Fact]
    public async Task ListFiles_EmptyStore_ReturnsEmptyListAsync()
    {
        // Arrange
        var tools = await CreateToolsAsync();
        var listFiles = GetTool(tools, "FileAccess_ListFiles");

        // Act
        var result = await InvokeToolAsync(listFiles, new AIFunctionArguments());

        // Assert
        var entries = Assert.IsType<JsonElement>(result).EnumerateArray().ToList();
        Assert.Empty(entries);
    }

    #endregion

    #region SearchFiles Tests

    [Fact]
    public async Task SearchFiles_FindsMatchingContentAsync()
    {
        // Arrange
        var store = new InMemoryAgentFileStore();
        await store.WriteFileAsync("notes.md", "Important research findings about AI");
        var tools = await CreateToolsAsync(store);
        var searchFiles = GetTool(tools, "FileAccess_SearchFiles");

        // Act
        var result = await InvokeToolAsync(searchFiles, new AIFunctionArguments
        {
            ["regexPattern"] = "research findings",
            ["filePattern"] = "",
        });

        // Assert
        var entries = Assert.IsType<JsonElement>(result).EnumerateArray().ToList();
        Assert.Single(entries);
        Assert.Equal("notes.md", entries[0].GetProperty("fileName").GetString());
        Assert.True(entries[0].TryGetProperty("matchingLines", out var matchingLines));
        Assert.True(matchingLines.GetArrayLength() > 0);
    }

    [Fact]
    public async Task SearchFiles_WithFilePattern_FiltersResultsAsync()
    {
        // Arrange
        var store = new InMemoryAgentFileStore();
        await store.WriteFileAsync("notes.md", "Important data");
        await store.WriteFileAsync("data.txt", "Important data");
        var tools = await CreateToolsAsync(store);
        var searchFiles = GetTool(tools, "FileAccess_SearchFiles");

        // Act
        var result = await InvokeToolAsync(searchFiles, new AIFunctionArguments
        {
            ["regexPattern"] = "Important",
            ["filePattern"] = "*.md",
        });

        // Assert
        var entries = Assert.IsType<JsonElement>(result).EnumerateArray().ToList();
        Assert.Single(entries);
        Assert.Equal("notes.md", entries[0].GetProperty("fileName").GetString());
    }

    [Fact]
    public async Task SearchFiles_NoMatches_ReturnsEmptyAsync()
    {
        // Arrange
        var store = new InMemoryAgentFileStore();
        await store.WriteFileAsync("notes.md", "No matching content here");
        var tools = await CreateToolsAsync(store);
        var searchFiles = GetTool(tools, "FileAccess_SearchFiles");

        // Act
        var result = await InvokeToolAsync(searchFiles, new AIFunctionArguments
        {
            ["regexPattern"] = "nonexistent pattern xyz",
        });

        // Assert
        var entries = Assert.IsType<JsonElement>(result).EnumerateArray().ToList();
        Assert.Empty(entries);
    }

    #endregion

    #region Path Traversal Protection

    [Fact]
    public async Task SaveFile_PathTraversal_ThrowsAsync()
    {
        // Arrange
        var tools = await CreateToolsAsync();
        var saveFile = GetTool(tools, "FileAccess_SaveFile");

        // Act & Assert
        await Assert.ThrowsAsync<ArgumentException>(async () =>
            await InvokeToolAsync(saveFile, new AIFunctionArguments
            {
                ["fileName"] = "../escape.md",
                ["content"] = "Content",
            }));
    }

    [Fact]
    public async Task SaveFile_AbsolutePath_ThrowsAsync()
    {
        // Arrange
        var tools = await CreateToolsAsync();
        var saveFile = GetTool(tools, "FileAccess_SaveFile");

        // Act & Assert
        await Assert.ThrowsAsync<ArgumentException>(async () =>
            await InvokeToolAsync(saveFile, new AIFunctionArguments
            {
                ["fileName"] = "/etc/passwd",
                ["content"] = "Content",
            }));
    }

    [Fact]
    public async Task SaveFile_DriveRootedPath_ThrowsAsync()
    {
        // Arrange
        var tools = await CreateToolsAsync();
        var saveFile = GetTool(tools, "FileAccess_SaveFile");

        // Act & Assert
        await Assert.ThrowsAsync<ArgumentException>(async () =>
            await InvokeToolAsync(saveFile, new AIFunctionArguments
            {
                ["fileName"] = "C:\\temp\\file.md",
                ["content"] = "Content",
            }));
    }

    [Fact]
    public async Task SaveFile_DoubleDotsInFileName_AllowedAsync()
    {
        // Arrange — "notes..md" is not a path traversal attempt.
        var store = new InMemoryAgentFileStore();
        var tools = await CreateToolsAsync(store);
        var saveFile = GetTool(tools, "FileAccess_SaveFile");

        // Act
        await InvokeToolAsync(saveFile, new AIFunctionArguments
        {
            ["fileName"] = "notes..md",
            ["content"] = "Content",
        });

        // Assert
        Assert.Equal("Content", await store.ReadFileAsync("notes..md"));
    }

    [Fact]
    public async Task ReadFile_PathTraversal_ThrowsAsync()
    {
        // Arrange
        var tools = await CreateToolsAsync();
        var readFile = GetTool(tools, "FileAccess_ReadFile");

        // Act & Assert
        await Assert.ThrowsAsync<ArgumentException>(async () =>
            await InvokeToolAsync(readFile, new AIFunctionArguments
            {
                ["fileName"] = "../../etc/passwd",
            }));
    }

    [Fact]
    public async Task DeleteFile_PathTraversal_ThrowsAsync()
    {
        // Arrange
        var tools = await CreateToolsAsync();
        var deleteFile = GetTool(tools, "FileAccess_DeleteFile");

        // Act & Assert
        await Assert.ThrowsAsync<ArgumentException>(async () =>
            await InvokeToolAsync(deleteFile, new AIFunctionArguments
            {
                ["fileName"] = "../escape.md",
            }));
    }

    #endregion

    #region Options Tests

    [Fact]
    public async Task Options_CustomInstructions_OverridesDefaultAsync()
    {
        // Arrange
        var options = new FileAccessProviderOptions { Instructions = "Custom file access instructions." };
        var provider = new FileAccessProvider(new InMemoryAgentFileStore(), options: options);
        var agent = new Mock<AIAgent>().Object;
        var session = new ChatClientAgentSession();
#pragma warning disable MAAI001
        var context = new AIContextProvider.InvokingContext(agent, session, new AIContext());
#pragma warning restore MAAI001

        // Act
        AIContext result = await provider.InvokingAsync(context);

        // Assert
        Assert.Equal("Custom file access instructions.", result.Instructions);
    }

    [Fact]
    public async Task Options_Null_UsesDefaultInstructionsAsync()
    {
        // Arrange
        var provider = new FileAccessProvider(new InMemoryAgentFileStore());
        var agent = new Mock<AIAgent>().Object;
        var session = new ChatClientAgentSession();
#pragma warning disable MAAI001
        var context = new AIContextProvider.InvokingContext(agent, session, new AIContext());
#pragma warning restore MAAI001

        // Act
        AIContext result = await provider.InvokingAsync(context);

        // Assert
        Assert.Contains("File Access", result.Instructions);
    }

    #endregion

    #region Helper Methods

    private static async Task<IEnumerable<AITool>> CreateToolsAsync(InMemoryAgentFileStore? store = null)
    {
        var provider = new FileAccessProvider(store ?? new InMemoryAgentFileStore());
        var agent = new Mock<AIAgent>().Object;
        var session = new ChatClientAgentSession();
#pragma warning disable MAAI001
        var context = new AIContextProvider.InvokingContext(agent, session, new AIContext());
#pragma warning restore MAAI001

        AIContext result = await provider.InvokingAsync(context);
        return result.Tools!;
    }

    private static AIFunction GetTool(IEnumerable<AITool> tools, string name)
    {
        return (AIFunction)tools.First(t => t is AIFunction f && f.Name == name);
    }

    /// <summary>
    /// Invokes a tool. Since <see cref="FileAccessProvider"/> does not use session state,
    /// the tools don't need an ambient <see cref="AIAgent.CurrentRunContext"/>.
    /// </summary>
    private static async Task<object?> InvokeToolAsync(AIFunction tool, AIFunctionArguments arguments)
    {
        return await tool.InvokeAsync(arguments);
    }

    #endregion
}
