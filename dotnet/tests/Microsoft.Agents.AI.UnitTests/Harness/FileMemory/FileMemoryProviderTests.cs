// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using Moq;

namespace Microsoft.Agents.AI.UnitTests.Harness.FileMemory;

public class FileMemoryProviderTests
{
    #region Constructor Validation

    [Fact]
    public void Constructor_NullFileStore_Throws()
    {
        Assert.Throws<ArgumentNullException>(() => new FileMemoryProvider(null!));
    }

    [Fact]
    public void Constructor_WithDefaults_Succeeds()
    {
        // Act
        var provider = new FileMemoryProvider(new InMemoryAgentFileStore());

        // Assert
        Assert.NotNull(provider);
    }

    [Fact]
    public void Constructor_WithStateInitializer_Succeeds()
    {
        // Act
        var provider = new FileMemoryProvider(
            new InMemoryAgentFileStore(),
            _ => new FileMemoryState { WorkingFolder = "custom" });

        // Assert
        Assert.NotNull(provider);
    }

    #endregion

    #region ProvideAIContextAsync Tests

    [Fact]
    public async Task ProvideAIContextAsync_ReturnsToolsAsync()
    {
        // Arrange
        var (tools, _, session) = await CreateToolsAsync();

        // Assert - 5 tools: SaveFile, ReadFile, DeleteFile, ListFiles, SearchFiles
        Assert.Equal(5, tools.Count());
    }

    [Fact]
    public async Task ProvideAIContextAsync_ReturnsInstructionsAsync()
    {
        // Arrange
        var provider = new FileMemoryProvider(new InMemoryAgentFileStore());
        var agent = new Mock<AIAgent>().Object;
        var session = new ChatClientAgentSession();
#pragma warning disable MAAI001
        var context = new AIContextProvider.InvokingContext(agent, session, new AIContext());
#pragma warning restore MAAI001

        // Act
        AIContext result = await provider.InvokingAsync(context);

        // Assert
        Assert.NotNull(result.Instructions);
        Assert.Contains("file-based memory", result.Instructions);
        Assert.Contains("compacted", result.Instructions);
    }

    #endregion

    #region SaveFile Tests

    [Fact]
    public async Task SaveFile_CreatesFileAsync()
    {
        // Arrange
        var store = new InMemoryAgentFileStore();
        var (tools, _, session) = await CreateToolsAsync(store);
        var saveFile = GetTool(tools, "FileMemory_SaveFile");

        // Act
        await InvokeWithRunContextAsync(saveFile, new AIFunctionArguments
        {
            ["fileName"] = "notes.md",
            ["content"] = "Test content",
            ["description"] = "",
        }, session);

        // Assert
        var content = await store.ReadFileAsync("notes.md");
        Assert.Equal("Test content", content);
    }

    [Fact]
    public async Task SaveFile_WithDescription_CreatesBothFilesAsync()
    {
        // Arrange
        var store = new InMemoryAgentFileStore();
        var (tools, _, session) = await CreateToolsAsync(store);
        var saveFile = GetTool(tools, "FileMemory_SaveFile");

        // Act
        await InvokeWithRunContextAsync(saveFile, new AIFunctionArguments
        {
            ["fileName"] = "research.md",
            ["content"] = "Long research content...",
            ["description"] = "Summary of research findings",
        }, session);

        // Assert
        var content = await store.ReadFileAsync("research.md");
        Assert.Equal("Long research content...", content);
        var desc = await store.ReadFileAsync("research_description.md");
        Assert.Equal("Summary of research findings", desc);
    }

    [Fact]
    public async Task SaveFile_WithoutDescription_DeletesStaleDescriptionAsync()
    {
        // Arrange
        var store = new InMemoryAgentFileStore();
        var (tools, _, session) = await CreateToolsAsync(store);
        var saveFile = GetTool(tools, "FileMemory_SaveFile");

        // Save with description first.
        await InvokeWithRunContextAsync(saveFile, new AIFunctionArguments
        {
            ["fileName"] = "notes.md",
            ["content"] = "Original",
            ["description"] = "Old description",
        }, session);
        Assert.NotNull(await store.ReadFileAsync("notes_description.md"));

        // Act — overwrite without description.
        await InvokeWithRunContextAsync(saveFile, new AIFunctionArguments
        {
            ["fileName"] = "notes.md",
            ["content"] = "Updated",
        }, session);

        // Assert — stale description file is removed.
        Assert.Equal("Updated", await store.ReadFileAsync("notes.md"));
        Assert.Null(await store.ReadFileAsync("notes_description.md"));
    }

    [Fact]
    public async Task SaveFile_WithCustomState_CreatesInSubfolderAsync()
    {
        // Arrange
        var store = new InMemoryAgentFileStore();
        var (tools, state, session) = await CreateToolsAsync(store, _ => new FileMemoryState { WorkingFolder = "session123" });
        var saveFile = GetTool(tools, "FileMemory_SaveFile");

        // Act
        await InvokeWithRunContextAsync(saveFile, new AIFunctionArguments
        {
            ["fileName"] = "notes.md",
            ["content"] = "Session content",
            ["description"] = "",
        }, session);

        // Assert
        Assert.Equal("session123", state.WorkingFolder);
        var content = await store.ReadFileAsync("session123/notes.md");
        Assert.Equal("Session content", content);
    }

    #endregion

    #region ReadFile Tests

    [Fact]
    public async Task ReadFile_ExistingFile_ReturnsContentAsync()
    {
        // Arrange
        var store = new InMemoryAgentFileStore();
        await store.WriteFileAsync("notes.md", "Stored content");
        var (tools, _, session) = await CreateToolsAsync(store);
        var readFile = GetTool(tools, "FileMemory_ReadFile");

        // Act
        var result = await InvokeWithRunContextAsync(readFile, new AIFunctionArguments
        {
            ["fileName"] = "notes.md",
        }, session);

        // Assert
        var text = Assert.IsType<JsonElement>(result).GetString();
        Assert.Equal("Stored content", text);
    }

    [Fact]
    public async Task ReadFile_NonExistent_ReturnsNotFoundMessageAsync()
    {
        // Arrange
        var (tools, _, session) = await CreateToolsAsync();
        var readFile = GetTool(tools, "FileMemory_ReadFile");

        // Act
        var result = await InvokeWithRunContextAsync(readFile, new AIFunctionArguments
        {
            ["fileName"] = "nonexistent.md",
        }, session);

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
        var (tools, _, session) = await CreateToolsAsync(store);
        var deleteFile = GetTool(tools, "FileMemory_DeleteFile");

        // Act
        var result = await InvokeWithRunContextAsync(deleteFile, new AIFunctionArguments
        {
            ["fileName"] = "notes.md",
        }, session);

        // Assert
        var text = Assert.IsType<JsonElement>(result).GetString();
        Assert.Contains("deleted", text);
        Assert.False(await store.FileExistsAsync("notes.md"));
    }

    [Fact]
    public async Task DeleteFile_AlsoDeletesDescriptionFileAsync()
    {
        // Arrange
        var store = new InMemoryAgentFileStore();
        await store.WriteFileAsync("notes.md", "Content");
        await store.WriteFileAsync("notes_description.md", "Description");
        var (tools, _, session) = await CreateToolsAsync(store);
        var deleteFile = GetTool(tools, "FileMemory_DeleteFile");

        // Act
        await InvokeWithRunContextAsync(deleteFile, new AIFunctionArguments
        {
            ["fileName"] = "notes.md",
        }, session);

        // Assert
        Assert.False(await store.FileExistsAsync("notes.md"));
        Assert.False(await store.FileExistsAsync("notes_description.md"));
    }

    #endregion

    #region ListFiles Tests

    [Fact]
    public async Task ListFiles_ReturnsFilesWithDescriptionsAsync()
    {
        // Arrange
        var store = new InMemoryAgentFileStore();
        await store.WriteFileAsync("notes.md", "Content");
        await store.WriteFileAsync("notes_description.md", "A description");
        await store.WriteFileAsync("other.md", "Other content");
        var (tools, _, session) = await CreateToolsAsync(store);
        var listFiles = GetTool(tools, "FileMemory_ListFiles");

        // Act
        var result = await InvokeWithRunContextAsync(listFiles, new AIFunctionArguments(), session);

        // Assert
        var entries = Assert.IsType<JsonElement>(result).EnumerateArray().ToList();
        Assert.Equal(2, entries.Count);

        var notesEntry = entries.First(e => e.GetProperty("fileName").GetString() == "notes.md");
        Assert.Equal("A description", notesEntry.GetProperty("description").GetString());

        var otherEntry = entries.First(e => e.GetProperty("fileName").GetString() == "other.md");
        Assert.False(otherEntry.TryGetProperty("description", out _));
    }

    [Fact]
    public async Task ListFiles_HidesDescriptionFilesAsync()
    {
        // Arrange
        var store = new InMemoryAgentFileStore();
        await store.WriteFileAsync("notes.md", "Content");
        await store.WriteFileAsync("notes_description.md", "Desc");
        var (tools, _, session) = await CreateToolsAsync(store);
        var listFiles = GetTool(tools, "FileMemory_ListFiles");

        // Act
        var result = await InvokeWithRunContextAsync(listFiles, new AIFunctionArguments(), session);

        // Assert
        var entries = Assert.IsType<JsonElement>(result).EnumerateArray().ToList();
        Assert.Single(entries);
        Assert.Equal("notes.md", entries[0].GetProperty("fileName").GetString());
    }

    #endregion

    #region SearchFiles Tests

    [Fact]
    public async Task SearchFiles_FindsMatchingContentAsync()
    {
        // Arrange
        var store = new InMemoryAgentFileStore();
        await store.WriteFileAsync("notes.md", "Important research findings about AI");
        var (tools, _, session) = await CreateToolsAsync(store);
        var searchFiles = GetTool(tools, "FileMemory_SearchFiles");

        // Act
        var result = await InvokeWithRunContextAsync(searchFiles, new AIFunctionArguments
        {
            ["regexPattern"] = "research findings",
            ["filePattern"] = "",
        }, session);

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
        var (tools, _, session) = await CreateToolsAsync(store);
        var searchFiles = GetTool(tools, "FileMemory_SearchFiles");

        // Act
        var result = await InvokeWithRunContextAsync(searchFiles, new AIFunctionArguments
        {
            ["regexPattern"] = "Important",
            ["filePattern"] = "*.md",
        }, session);

        // Assert
        var entries = Assert.IsType<JsonElement>(result).EnumerateArray().ToList();
        Assert.Single(entries);
        Assert.Equal("notes.md", entries[0].GetProperty("fileName").GetString());
    }

    #endregion

    #region State Initializer Tests

    [Fact]
    public async Task CustomStateInitializer_SetsWorkingFolderAsync()
    {
        // Arrange
        var store = new InMemoryAgentFileStore();
        var (_, state, _) = await CreateToolsAsync(store, _ => new FileMemoryState { WorkingFolder = "user42" });

        // Assert
        Assert.Equal("user42", state.WorkingFolder);
    }

    [Fact]
    public async Task DefaultStateInitializer_UsesEmptyWorkingFolderAsync()
    {
        // Arrange
        var (_, state, _) = await CreateToolsAsync();

        // Assert
        Assert.Equal(string.Empty, state.WorkingFolder);
    }

    [Fact]
    public async Task State_PersistsAcrossInvocationsAsync()
    {
        // Arrange
        var store = new InMemoryAgentFileStore();
        var provider = new FileMemoryProvider(store, _ => new FileMemoryState { WorkingFolder = "persistent" });
        var agent = new Mock<AIAgent>().Object;
        var session = new ChatClientAgentSession();
#pragma warning disable MAAI001
        var context = new AIContextProvider.InvokingContext(agent, session, new AIContext());
#pragma warning restore MAAI001

        // Act - first invocation initializes state
        await provider.InvokingAsync(context);
        session.StateBag.TryGetValue<FileMemoryState>("FileMemoryProvider", out var state1, AgentJsonUtilities.DefaultOptions);

        // Second invocation should reuse the same folder
        await provider.InvokingAsync(context);
        session.StateBag.TryGetValue<FileMemoryState>("FileMemoryProvider", out var state2, AgentJsonUtilities.DefaultOptions);

        // Assert
        Assert.NotNull(state1);
        Assert.NotNull(state2);
        Assert.Equal(state1!.WorkingFolder, state2!.WorkingFolder);
    }

    #endregion

    #region Path Traversal Protection

    [Fact]
    public async Task SaveFile_PathTraversal_ThrowsAsync()
    {
        // Arrange
        var (tools, _, session) = await CreateToolsAsync();
        var saveFile = GetTool(tools, "FileMemory_SaveFile");

        // Act & Assert
        await Assert.ThrowsAsync<ArgumentException>(async () =>
            await InvokeWithRunContextAsync(saveFile, new AIFunctionArguments
            {
                ["fileName"] = "../escape.md",
                ["content"] = "Content",
                ["description"] = "",
            }, session));
    }

    [Fact]
    public async Task SaveFile_AbsolutePath_ThrowsAsync()
    {
        // Arrange
        var (tools, _, session) = await CreateToolsAsync();
        var saveFile = GetTool(tools, "FileMemory_SaveFile");

        // Act & Assert
        await Assert.ThrowsAsync<ArgumentException>(async () =>
            await InvokeWithRunContextAsync(saveFile, new AIFunctionArguments
            {
                ["fileName"] = "/etc/passwd",
                ["content"] = "Content",
                ["description"] = "",
            }, session));
    }

    [Fact]
    public async Task SaveFile_DriveRootedPath_ThrowsAsync()
    {
        // Arrange
        var (tools, _, session) = await CreateToolsAsync();
        var saveFile = GetTool(tools, "FileMemory_SaveFile");

        // Act & Assert
        await Assert.ThrowsAsync<ArgumentException>(async () =>
            await InvokeWithRunContextAsync(saveFile, new AIFunctionArguments
            {
                ["fileName"] = "C:\\temp\\file.md",
                ["content"] = "Content",
            }, session));
    }

    [Fact]
    public async Task SaveFile_DoubleDotsInFileName_AllowedAsync()
    {
        // Arrange — "notes..md" is not a path traversal attempt.
        var store = new InMemoryAgentFileStore();
        var (tools, _, session) = await CreateToolsAsync(store);
        var saveFile = GetTool(tools, "FileMemory_SaveFile");

        // Act
        await InvokeWithRunContextAsync(saveFile, new AIFunctionArguments
        {
            ["fileName"] = "notes..md",
            ["content"] = "Content",
        }, session);

        // Assert
        Assert.Equal("Content", await store.ReadFileAsync("notes..md"));
    }

    #endregion

    #region Memory Index Tests

    [Fact]
    public async Task SaveFile_CreatesMemoryIndexAsync()
    {
        // Arrange
        var store = new InMemoryAgentFileStore();
        var (tools, _, session) = await CreateToolsAsync(store);
        var saveFile = GetTool(tools, "FileMemory_SaveFile");

        // Act
        await InvokeWithRunContextAsync(saveFile, new AIFunctionArguments
        {
            ["fileName"] = "notes.md",
            ["content"] = "Test content",
        }, session);

        // Assert — memories.md should exist and contain the file entry.
        string? index = await store.ReadFileAsync("memories.md");
        Assert.NotNull(index);
        Assert.Contains("**notes.md**", index);
    }

    [Fact]
    public async Task SaveFile_WithDescription_IndexIncludesDescriptionAsync()
    {
        // Arrange
        var store = new InMemoryAgentFileStore();
        var (tools, _, session) = await CreateToolsAsync(store);
        var saveFile = GetTool(tools, "FileMemory_SaveFile");

        // Act
        await InvokeWithRunContextAsync(saveFile, new AIFunctionArguments
        {
            ["fileName"] = "research.md",
            ["content"] = "Research data",
            ["description"] = "Key findings",
        }, session);

        // Assert
        string? index = await store.ReadFileAsync("memories.md");
        Assert.NotNull(index);
        Assert.Contains("**research.md**: Key findings", index);
    }

    [Fact]
    public async Task DeleteFile_UpdatesMemoryIndexAsync()
    {
        // Arrange
        var store = new InMemoryAgentFileStore();
        var (tools, _, session) = await CreateToolsAsync(store);
        var saveFile = GetTool(tools, "FileMemory_SaveFile");
        var deleteFile = GetTool(tools, "FileMemory_DeleteFile");

        await InvokeWithRunContextAsync(saveFile, new AIFunctionArguments
        {
            ["fileName"] = "notes.md",
            ["content"] = "Content",
        }, session);

        await InvokeWithRunContextAsync(saveFile, new AIFunctionArguments
        {
            ["fileName"] = "other.md",
            ["content"] = "Other",
        }, session);

        // Act
        await InvokeWithRunContextAsync(deleteFile, new AIFunctionArguments
        {
            ["fileName"] = "notes.md",
        }, session);

        // Assert — index should only contain other.md
        string? index = await store.ReadFileAsync("memories.md");
        Assert.NotNull(index);
        Assert.DoesNotContain("notes.md", index);
        Assert.Contains("**other.md**", index);
    }

    [Fact]
    public async Task MemoryIndex_CappedAt50EntriesAsync()
    {
        // Arrange
        var store = new InMemoryAgentFileStore();
        var (tools, _, session) = await CreateToolsAsync(store);
        var saveFile = GetTool(tools, "FileMemory_SaveFile");

        // Act — save 55 files
        for (int i = 0; i < 55; i++)
        {
            await InvokeWithRunContextAsync(saveFile, new AIFunctionArguments
            {
                ["fileName"] = $"file{i:D3}.md",
                ["content"] = $"Content {i}",
            }, session);
        }

        // Assert — index should have at most 50 entries
        string? index = await store.ReadFileAsync("memories.md");
        Assert.NotNull(index);

        int entryCount = 0;
        foreach (string line in index!.Split('\n'))
        {
            if (line.StartsWith("- **", StringComparison.Ordinal))
            {
                entryCount++;
            }
        }

        Assert.Equal(50, entryCount);
    }

    [Fact]
    public async Task ListFiles_HidesMemoryIndexAsync()
    {
        // Arrange
        var store = new InMemoryAgentFileStore();
        var (tools, _, session) = await CreateToolsAsync(store);
        var saveFile = GetTool(tools, "FileMemory_SaveFile");
        var listFiles = GetTool(tools, "FileMemory_ListFiles");

        await InvokeWithRunContextAsync(saveFile, new AIFunctionArguments
        {
            ["fileName"] = "notes.md",
            ["content"] = "Content",
        }, session);

        // Act
        var result = await InvokeWithRunContextAsync(listFiles, new AIFunctionArguments(), session);

        // Assert — memories.md should not appear in the listing
        var entries = Assert.IsType<JsonElement>(result).EnumerateArray().ToList();
        Assert.Single(entries);
        Assert.Equal("notes.md", entries[0].GetProperty("fileName").GetString());
    }

    [Fact]
    public async Task ProvideAIContextAsync_InjectsMemoryIndexMessageAsync()
    {
        // Arrange
        var store = new InMemoryAgentFileStore();
        var provider = new FileMemoryProvider(store);
        var agent = new Mock<AIAgent>().Object;
        var session = new ChatClientAgentSession();

        // First, save a file via tool invocation to create the index.
#pragma warning disable MAAI001
        var initContext = new AIContextProvider.InvokingContext(agent, session, new AIContext());
#pragma warning restore MAAI001
        AIContext initResult = await provider.InvokingAsync(initContext);
        var saveFile = GetTool(initResult.Tools!, "FileMemory_SaveFile");
        await InvokeWithRunContextAsync(saveFile, new AIFunctionArguments
        {
            ["fileName"] = "research.md",
            ["content"] = "Data",
            ["description"] = "Research summary",
        }, session);

        // Act — invoke the provider again; it should now inject the memory index.
#pragma warning disable MAAI001
        var context = new AIContextProvider.InvokingContext(agent, session, new AIContext());
#pragma warning restore MAAI001
        AIContext result = await provider.InvokingAsync(context);

        // Assert
        Assert.NotNull(result.Messages);
        var messages = result.Messages!.ToList();
        Assert.Single(messages);
        Assert.Equal(ChatRole.User, messages[0].Role);
        Assert.Contains("memory index", messages[0].Text, StringComparison.OrdinalIgnoreCase);
        Assert.Contains("research.md", messages[0].Text);
    }

    [Fact]
    public async Task ProvideAIContextAsync_NoFiles_NoMessageInjectedAsync()
    {
        // Arrange
        var provider = new FileMemoryProvider(new InMemoryAgentFileStore());
        var agent = new Mock<AIAgent>().Object;
        var session = new ChatClientAgentSession();
#pragma warning disable MAAI001
        var context = new AIContextProvider.InvokingContext(agent, session, new AIContext());
#pragma warning restore MAAI001

        // Act
        AIContext result = await provider.InvokingAsync(context);

        // Assert — no memories.md exists, so no message should be injected
        Assert.Null(result.Messages);
    }

    #endregion

    #region Helper Methods

    private static FileMemoryProvider CreateProvider(InMemoryAgentFileStore? store = null, Func<AgentSession?, FileMemoryState>? stateInitializer = null)
    {
        return new FileMemoryProvider(store ?? new InMemoryAgentFileStore(), stateInitializer);
    }

    private static async Task<(IEnumerable<AITool> Tools, FileMemoryState State, AgentSession Session)> CreateToolsAsync(InMemoryAgentFileStore? store = null, Func<AgentSession?, FileMemoryState>? stateInitializer = null)
    {
        var provider = CreateProvider(store, stateInitializer);
        var agent = new Mock<AIAgent>().Object;
        var session = new ChatClientAgentSession();
#pragma warning disable MAAI001
        var context = new AIContextProvider.InvokingContext(agent, session, new AIContext());
#pragma warning restore MAAI001

        AIContext result = await provider.InvokingAsync(context);

        session.StateBag.TryGetValue<FileMemoryState>("FileMemoryProvider", out var state, AgentJsonUtilities.DefaultOptions);

        return (result.Tools!, state!, session);
    }

    private static AIFunction GetTool(IEnumerable<AITool> tools, string name)
    {
        return (AIFunction)tools.First(t => t is AIFunction f && f.Name == name);
    }

    /// <summary>
    /// Invokes a tool within a mock <see cref="AIAgent.CurrentRunContext"/> so that
    /// the tool methods can access the session via <c>AIAgent.CurrentRunContext?.Session</c>.
    /// </summary>
    /// <param name="tool">The tool to invoke.</param>
    /// <param name="arguments">The arguments to pass to the tool.</param>
    /// <param name="session">
    /// An optional session to use in the run context. When provided, ensures the tool executes
    /// against the same session whose state was initialized during <see cref="CreateToolsAsync"/>.
    /// When <see langword="null"/>, a new session is created.
    /// </param>
    private static async Task<object?> InvokeWithRunContextAsync(AIFunction tool, AIFunctionArguments arguments, AgentSession? session = null)
    {
        var agent = new Mock<AIAgent>().Object;
        session ??= new ChatClientAgentSession();
        var messages = new List<ChatMessage>();

        // Set up the ambient run context so tool methods can access the session.
        var runContext = new AgentRunContext(agent, session, messages, null);

        // Use reflection to set the protected static CurrentRunContext property.
        var property = typeof(AIAgent).GetProperty("CurrentRunContext", System.Reflection.BindingFlags.Public | System.Reflection.BindingFlags.Static);
        var setter = property!.GetSetMethod(true)!;
        var previousContext = AIAgent.CurrentRunContext;
        try
        {
            setter.Invoke(null, [runContext]);
            return await tool.InvokeAsync(arguments);
        }
        finally
        {
            setter.Invoke(null, [previousContext]);
        }
    }

    #endregion

    #region Options Tests

    /// <summary>
    /// Verify that custom instructions override the default.
    /// </summary>
    [Fact]
    public async Task Options_CustomInstructions_OverridesDefaultAsync()
    {
        // Arrange
        var options = new FileMemoryProviderOptions { Instructions = "Custom file memory instructions." };
        var provider = new FileMemoryProvider(new InMemoryAgentFileStore(), options: options);
        var agent = new Mock<AIAgent>().Object;
        var session = new ChatClientAgentSession();
#pragma warning disable MAAI001
        var context = new AIContextProvider.InvokingContext(agent, session, new AIContext());
#pragma warning restore MAAI001

        // Act
        AIContext result = await provider.InvokingAsync(context);

        // Assert
        Assert.Equal("Custom file memory instructions.", result.Instructions);
    }

    /// <summary>
    /// Verify that null options uses default instructions.
    /// </summary>
    [Fact]
    public async Task Options_Null_UsesDefaultInstructionsAsync()
    {
        // Arrange
        var provider = new FileMemoryProvider(new InMemoryAgentFileStore());
        var agent = new Mock<AIAgent>().Object;
        var session = new ChatClientAgentSession();
#pragma warning disable MAAI001
        var context = new AIContextProvider.InvokingContext(agent, session, new AIContext());
#pragma warning restore MAAI001

        // Act
        AIContext result = await provider.InvokingAsync(context);

        // Assert
        Assert.Contains("file-based memory", result.Instructions);
    }

    #endregion

    #region Thread Safety Tests

    [Fact]
    public async Task ConcurrentSaves_ProduceConsistentIndexAsync()
    {
        // Arrange
        var store = new InMemoryAgentFileStore();
        var (tools, _, session) = await CreateToolsAsync(store);
        var saveFile = GetTool(tools, "FileMemory_SaveFile");
        const int FileCount = 20;

        // Act — save multiple files in parallel.
        var tasks = new Task[FileCount];
        for (int i = 0; i < FileCount; i++)
        {
            int index = i;
            tasks[i] = InvokeWithRunContextAsync(saveFile, new AIFunctionArguments
            {
                ["fileName"] = $"file{index}.md",
                ["content"] = $"Content {index}",
                ["description"] = $"Description {index}",
            }, session);
        }

        await Task.WhenAll(tasks);

        // Assert — the memory index should contain all files.
        string? indexContent = await store.ReadFileAsync("memories.md");
        Assert.NotNull(indexContent);
        for (int i = 0; i < FileCount; i++)
        {
            Assert.Contains($"**file{i}.md**", indexContent);
        }
    }

    [Fact]
    public async Task ConcurrentSaveAndDelete_ProduceConsistentIndexAsync()
    {
        // Arrange — pre-populate files that will be deleted.
        var store = new InMemoryAgentFileStore();
        var (tools, _, session) = await CreateToolsAsync(store);
        var saveFile = GetTool(tools, "FileMemory_SaveFile");
        var deleteFile = GetTool(tools, "FileMemory_DeleteFile");

        for (int i = 0; i < 5; i++)
        {
            await InvokeWithRunContextAsync(saveFile, new AIFunctionArguments
            {
                ["fileName"] = $"delete{i}.md",
                ["content"] = $"To be deleted {i}",
            }, session);
        }

        // Act — concurrently save new files and delete existing ones.
        var tasks = new List<Task>();
        for (int i = 0; i < 5; i++)
        {
            int index = i;
            tasks.Add(InvokeWithRunContextAsync(saveFile, new AIFunctionArguments
            {
                ["fileName"] = $"keep{index}.md",
                ["content"] = $"Kept {index}",
            }, session));
            tasks.Add(InvokeWithRunContextAsync(deleteFile, new AIFunctionArguments
            {
                ["fileName"] = $"delete{index}.md",
            }, session));
        }

        await Task.WhenAll(tasks);

        // Assert — index should contain only the kept files.
        string? indexContent = await store.ReadFileAsync("memories.md");
        Assert.NotNull(indexContent);
        for (int i = 0; i < 5; i++)
        {
            Assert.Contains($"**keep{i}.md**", indexContent);
            Assert.DoesNotContain($"**delete{i}.md**", indexContent);
        }
    }

    [Fact]
    public void Dispose_ReleasesResources()
    {
        // Arrange
        var provider = new FileMemoryProvider(new InMemoryAgentFileStore());

        // Act
        provider.Dispose();

        // Assert — calling Dispose again should not throw (idempotent SemaphoreSlim.Dispose).
        provider.Dispose();
    }

    [Fact]
    public async Task SaveFile_AfterDispose_ThrowsAsync()
    {
        // Arrange — create tools from a provider, then dispose the provider.
        var store = new InMemoryAgentFileStore();
        var provider = CreateProvider(store);
        var agent = new Mock<AIAgent>().Object;
        var session = new ChatClientAgentSession();
#pragma warning disable MAAI001
        var context = new AIContextProvider.InvokingContext(agent, session, new AIContext());
#pragma warning restore MAAI001
        AIContext result = await provider.InvokingAsync(context);
        var saveFile = GetTool(result.Tools!, "FileMemory_SaveFile");
        provider.Dispose();

        // Act & Assert — the disposed SemaphoreSlim should throw ObjectDisposedException.
        await Assert.ThrowsAsync<ObjectDisposedException>(async () =>
            await InvokeWithRunContextAsync(saveFile, new AIFunctionArguments
            {
                ["fileName"] = "notes.md",
                ["content"] = "Should fail",
            }, session));
    }

    #endregion
}
