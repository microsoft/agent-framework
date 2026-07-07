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

        // Assert — 7 tools: Read, Ls, Grep, Write, Delete, Replace, ReplaceLines
        Assert.Equal(7, tools.Count());
    }

    #endregion

    #region Tool Approval

    [Fact]
    public async Task ProvideAIContextAsync_AllToolsRequireApprovalAsync()
    {
        // Arrange
        var tools = await CreateToolsAsync();

        // Assert — every tool is wrapped so that it always requires approval.
        Assert.Equal(7, tools.Count());
        Assert.All(tools, tool => Assert.IsType<ApprovalRequiredAIFunction>(tool));
    }

    [Fact]
    public async Task DisableReadOnlyToolApproval_ReadOnlyToolsNotWrappedAsync()
    {
        // Arrange
        var tools = (await CreateToolsAsync(new FileAccessProviderOptions { DisableReadOnlyToolApproval = true })).ToList();

        // Assert — read-only tools are bare functions; store-modifying tools still require approval.
        AssertRequiresApproval(tools, FileAccessProvider.ReadFileToolName, expected: false);
        AssertRequiresApproval(tools, FileAccessProvider.LsToolName, expected: false);
        AssertRequiresApproval(tools, FileAccessProvider.GrepToolName, expected: false);
        AssertRequiresApproval(tools, FileAccessProvider.WriteToolName, expected: true);
        AssertRequiresApproval(tools, FileAccessProvider.DeleteFileToolName, expected: true);
        AssertRequiresApproval(tools, FileAccessProvider.ReplaceToolName, expected: true);
        AssertRequiresApproval(tools, FileAccessProvider.ReplaceLinesToolName, expected: true);
    }

    [Fact]
    public async Task DisableWriteToolApproval_WriteToolsNotWrappedAsync()
    {
        // Arrange
        var tools = (await CreateToolsAsync(new FileAccessProviderOptions { DisableWriteToolApproval = true })).ToList();

        // Assert — store-modifying tools are bare functions; read-only tools still require approval.
        AssertRequiresApproval(tools, FileAccessProvider.ReadFileToolName, expected: true);
        AssertRequiresApproval(tools, FileAccessProvider.LsToolName, expected: true);
        AssertRequiresApproval(tools, FileAccessProvider.GrepToolName, expected: true);
        AssertRequiresApproval(tools, FileAccessProvider.WriteToolName, expected: false);
        AssertRequiresApproval(tools, FileAccessProvider.DeleteFileToolName, expected: false);
        AssertRequiresApproval(tools, FileAccessProvider.ReplaceToolName, expected: false);
        AssertRequiresApproval(tools, FileAccessProvider.ReplaceLinesToolName, expected: false);
    }

    [Fact]
    public async Task DisableBothToolApprovals_NoToolsWrappedAsync()
    {
        // Arrange
        var tools = (await CreateToolsAsync(new FileAccessProviderOptions
        {
            DisableReadOnlyToolApproval = true,
            DisableWriteToolApproval = true,
        })).ToList();

        // Assert — no tool requires approval.
        Assert.Equal(7, tools.Count);
        Assert.DoesNotContain(tools, tool => tool is ApprovalRequiredAIFunction);
    }

    private static void AssertRequiresApproval(IEnumerable<AITool> tools, string toolName, bool expected)
    {
        var tool = tools.OfType<AIFunction>().First(t => t.Name == toolName);
        Assert.Equal(expected, tool is ApprovalRequiredAIFunction);
    }

    [Theory]
    [InlineData(FileAccessProvider.ReadFileToolName, true)]
    [InlineData(FileAccessProvider.LsToolName, true)]
    [InlineData(FileAccessProvider.GrepToolName, true)]
    [InlineData(FileAccessProvider.WriteToolName, false)]
    [InlineData(FileAccessProvider.DeleteFileToolName, false)]
    [InlineData(FileAccessProvider.ReplaceToolName, false)]
    [InlineData(FileAccessProvider.ReplaceLinesToolName, false)]
    [InlineData("some_other_tool", false)]
    public async Task ReadOnlyToolsAutoApprovalRule_ApprovesOnlyReadOnlyToolsAsync(string toolName, bool expected)
    {
        // Arrange
        var functionCall = new FunctionCallContent("call1", toolName);

        // Act
        bool approved = await FileAccessProvider.ReadOnlyToolsAutoApprovalRule(functionCall);

        // Assert
        Assert.Equal(expected, approved);
    }

    [Theory]
    [InlineData(FileAccessProvider.ReadFileToolName, true)]
    [InlineData(FileAccessProvider.LsToolName, true)]
    [InlineData(FileAccessProvider.GrepToolName, true)]
    [InlineData(FileAccessProvider.WriteToolName, true)]
    [InlineData(FileAccessProvider.DeleteFileToolName, true)]
    [InlineData(FileAccessProvider.ReplaceToolName, true)]
    [InlineData(FileAccessProvider.ReplaceLinesToolName, true)]
    [InlineData("some_other_tool", false)]
    public async Task AllToolsAutoApprovalRule_ApprovesAllFileAccessToolsAsync(string toolName, bool expected)
    {
        // Arrange
        var functionCall = new FunctionCallContent("call1", toolName);

        // Act
        bool approved = await FileAccessProvider.AllToolsAutoApprovalRule(functionCall);

        // Assert
        Assert.Equal(expected, approved);
    }

    #endregion

    #region ProvideAIContextAsync Tests (continued)

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
        Assert.Contains("file_access_", result.Instructions);
        Assert.Contains("persist beyond the current session", result.Instructions);
    }

    [Fact]
    public async Task ProvideAIContextAsync_DoesNotInjectMessagesAsync()
    {
        // Arrange — FileAccessProvider should never inject messages (unlike FileMemoryProvider).
        var store = new InMemoryAgentFileStore();
        await store.WriteAsync("notes.md", "Content");
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
        var saveFile = GetTool(tools, "file_access_write");

        // Act
        await InvokeToolAsync(saveFile, new AIFunctionArguments
        {
            ["fileName"] = "notes.md",
            ["content"] = "Test content",
        });

        // Assert
        var content = await store.ReadAsync("notes.md");
        Assert.Equal("Test content", content);
    }

    [Fact]
    public async Task SaveFile_DoesNotCreateDescriptionSidecarAsync()
    {
        // Arrange — FileAccessProvider should never create description sidecar files.
        var store = new InMemoryAgentFileStore();
        var tools = await CreateToolsAsync(store);
        var saveFile = GetTool(tools, "file_access_write");

        // Act
        await InvokeToolAsync(saveFile, new AIFunctionArguments
        {
            ["fileName"] = "research.md",
            ["content"] = "Long research content...",
        });

        // Assert — file exists, no description sidecar
        Assert.Equal("Long research content...", await store.ReadAsync("research.md"));
        Assert.Null(await store.ReadAsync("research_description.md"));
    }

    [Fact]
    public async Task SaveFile_ExistingFile_WithoutOverwrite_ReturnsErrorAsync()
    {
        // Arrange
        var store = new InMemoryAgentFileStore();
        var tools = await CreateToolsAsync(store);
        var saveFile = GetTool(tools, "file_access_write");

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
        Assert.Equal("Original", await store.ReadAsync("notes.md"));
        var text = Assert.IsType<JsonElement>(result).GetString();
        Assert.Contains("already exists", text);
    }

    [Fact]
    public async Task SaveFile_ExistingFile_WithOverwrite_SucceedsAsync()
    {
        // Arrange
        var store = new InMemoryAgentFileStore();
        var tools = await CreateToolsAsync(store);
        var saveFile = GetTool(tools, "file_access_write");

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
        Assert.Equal("Updated", await store.ReadAsync("notes.md"));
    }

    [Fact]
    public async Task SaveFile_ReturnsConfirmationAsync()
    {
        // Arrange
        var tools = await CreateToolsAsync();
        var saveFile = GetTool(tools, "file_access_write");

        // Act
        var result = await InvokeToolAsync(saveFile, new AIFunctionArguments
        {
            ["fileName"] = "test.md",
            ["content"] = "Content",
        });

        // Assert
        var text = Assert.IsType<JsonElement>(result).GetString();
        Assert.Contains("written", text);
    }

    #endregion

    #region ReadFile Tests

    [Fact]
    public async Task ReadFile_ExistingFile_ReturnsContentAsync()
    {
        // Arrange
        var store = new InMemoryAgentFileStore();
        await store.WriteAsync("notes.md", "Stored content");
        var tools = await CreateToolsAsync(store);
        var readFile = GetTool(tools, "file_access_read");

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
        var readFile = GetTool(tools, "file_access_read");

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
        await store.WriteAsync("notes.md", "Content");
        var tools = await CreateToolsAsync(store);
        var deleteFile = GetTool(tools, "file_access_delete");

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
        var deleteFile = GetTool(tools, "file_access_delete");

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

    #region Ls Tests

    [Fact]
    public async Task Ls_ReturnsFilesAndDirectoriesAsync()
    {
        // Arrange
        var store = new InMemoryAgentFileStore();
        await store.WriteAsync("notes.md", "Content");
        await store.WriteAsync("data.txt", "Data");
        await store.WriteAsync("reports/q1.md", "Q1");
        var tools = await CreateToolsAsync(store);
        var ls = GetTool(tools, "file_access_ls");

        // Act
        var result = await InvokeToolAsync(ls, new AIFunctionArguments());

        // Assert — each entry has a name and a type ("file" or "directory").
        var entries = Assert.IsType<JsonElement>(result).EnumerateArray().ToList();
        Assert.Equal(3, entries.Count);
        Assert.Contains(entries, e => e.GetProperty("name").GetString() == "reports" && e.GetProperty("type").GetString() == "directory");
        Assert.Contains(entries, e => e.GetProperty("name").GetString() == "data.txt" && e.GetProperty("type").GetString() == "file");
        Assert.Contains(entries, e => e.GetProperty("name").GetString() == "notes.md" && e.GetProperty("type").GetString() == "file");
    }

    [Fact]
    public async Task Ls_ListsSubdirectoriesBeforeFilesAsync()
    {
        // Arrange
        var store = new InMemoryAgentFileStore();
        await store.WriteAsync("a.txt", "A");
        await store.WriteAsync("reports/q1.md", "Q1");
        var tools = await CreateToolsAsync(store);
        var ls = GetTool(tools, "file_access_ls");

        // Act
        var result = await InvokeToolAsync(ls, new AIFunctionArguments());

        // Assert — subdirectories are listed before files.
        var entries = Assert.IsType<JsonElement>(result).EnumerateArray().ToList();
        Assert.Equal(2, entries.Count);
        Assert.Equal("directory", entries[0].GetProperty("type").GetString());
        Assert.Equal("file", entries[1].GetProperty("type").GetString());
    }

    [Fact]
    public async Task Ls_DoesNotFilterDescriptionFilesAsync()
    {
        // Arrange — FileAccessProvider doesn't know about description sidecars, so all files are visible.
        var store = new InMemoryAgentFileStore();
        await store.WriteAsync("notes.md", "Content");
        await store.WriteAsync("notes_description.md", "Description");
        var tools = await CreateToolsAsync(store);
        var ls = GetTool(tools, "file_access_ls");

        // Act
        var result = await InvokeToolAsync(ls, new AIFunctionArguments());

        // Assert — both files should be visible
        var entries = Assert.IsType<JsonElement>(result).EnumerateArray().ToList();
        Assert.Equal(2, entries.Count);
    }

    [Fact]
    public async Task Ls_EmptyStore_ReturnsEmptyListAsync()
    {
        // Arrange
        var tools = await CreateToolsAsync();
        var ls = GetTool(tools, "file_access_ls");

        // Act
        var result = await InvokeToolAsync(ls, new AIFunctionArguments());

        // Assert
        var entries = Assert.IsType<JsonElement>(result).EnumerateArray().ToList();
        Assert.Empty(entries);
    }

    [Fact]
    public async Task Ls_WithDirectory_ListsSubdirectoryChildrenAsync()
    {
        // Arrange
        var store = new InMemoryAgentFileStore();
        await store.WriteAsync("root.txt", "Root");
        await store.WriteAsync("reports/2024/q1.md", "Q1");
        await store.WriteAsync("reports/2024/q2.md", "Q2");
        var tools = await CreateToolsAsync(store);
        var ls = GetTool(tools, "file_access_ls");

        // Act
        var result = await InvokeToolAsync(ls, new AIFunctionArguments
        {
            ["directory"] = "reports/2024",
        });

        // Assert — only the direct children of reports/2024 are returned (by their names)
        var entries = Assert.IsType<JsonElement>(result).EnumerateArray().ToList();
        Assert.Equal(2, entries.Count);
        Assert.Contains(entries, e => e.GetProperty("name").GetString() == "q1.md");
        Assert.Contains(entries, e => e.GetProperty("name").GetString() == "q2.md");
    }

    [Fact]
    public async Task Ls_WithGlobPattern_FiltersEntriesAsync()
    {
        // Arrange
        var store = new InMemoryAgentFileStore();
        await store.WriteAsync("notes.md", "Content");
        await store.WriteAsync("data.txt", "Data");
        var tools = await CreateToolsAsync(store);
        var ls = GetTool(tools, "file_access_ls");

        // Act
        var result = await InvokeToolAsync(ls, new AIFunctionArguments
        {
            ["globPattern"] = "*.md",
        });

        // Assert — only entries matching the glob are returned
        var entries = Assert.IsType<JsonElement>(result).EnumerateArray().ToList();
        Assert.Single(entries);
        Assert.Equal("notes.md", entries[0].GetProperty("name").GetString());
    }

    [Fact]
    public async Task Ls_WithDirectory_ListsNestedSubdirectoriesAsync()
    {
        // Arrange
        var store = new InMemoryAgentFileStore();
        await store.WriteAsync("reports/q1.md", "Q1");
        await store.WriteAsync("reports/2024/q2.md", "Q2");
        await store.WriteAsync("reports/2025/q3.md", "Q3");
        var tools = await CreateToolsAsync(store);
        var ls = GetTool(tools, "file_access_ls");

        // Act
        var result = await InvokeToolAsync(ls, new AIFunctionArguments
        {
            ["directory"] = "reports",
        });

        // Assert — direct child subdirectories of reports plus the q1.md file
        var entries = Assert.IsType<JsonElement>(result).EnumerateArray().ToList();
        var directories = entries.Where(e => e.GetProperty("type").GetString() == "directory").Select(e => e.GetProperty("name").GetString()).ToList();
        Assert.Equal(2, directories.Count);
        Assert.Contains("2024", directories);
        Assert.Contains("2025", directories);
    }

    #endregion

    #region SearchFiles Tests

    [Fact]
    public async Task SearchFiles_FindsMatchingContentAsync()
    {
        // Arrange
        var store = new InMemoryAgentFileStore();
        await store.WriteAsync("notes.md", "Important research findings about AI");
        var tools = await CreateToolsAsync(store);
        var searchFiles = GetTool(tools, "file_access_grep");

        // Act
        var result = await InvokeToolAsync(searchFiles, new AIFunctionArguments
        {
            ["regexPattern"] = "research findings",
            ["globPattern"] = "",
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
        await store.WriteAsync("notes.md", "Important data");
        await store.WriteAsync("data.txt", "Important data");
        var tools = await CreateToolsAsync(store);
        var searchFiles = GetTool(tools, "file_access_grep");

        // Act
        var result = await InvokeToolAsync(searchFiles, new AIFunctionArguments
        {
            ["regexPattern"] = "Important",
            ["globPattern"] = "*.md",
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
        await store.WriteAsync("notes.md", "No matching content here");
        var tools = await CreateToolsAsync(store);
        var searchFiles = GetTool(tools, "file_access_grep");

        // Act
        var result = await InvokeToolAsync(searchFiles, new AIFunctionArguments
        {
            ["regexPattern"] = "nonexistent pattern xyz",
        });

        // Assert
        var entries = Assert.IsType<JsonElement>(result).EnumerateArray().ToList();
        Assert.Empty(entries);
    }

    [Fact]
    public async Task SearchFiles_SearchesAllDescendantsRecursivelyAsync()
    {
        // Arrange
        var store = new InMemoryAgentFileStore();
        await store.WriteAsync("root.md", "Important data at root");
        await store.WriteAsync("reports/q1.md", "Important data in reports");
        await store.WriteAsync("reports/2024/q2.md", "Important data nested deeper");
        var tools = await CreateToolsAsync(store);
        var searchFiles = GetTool(tools, "file_access_grep");

        // Act — no glob, so all descendants are searched
        var result = await InvokeToolAsync(searchFiles, new AIFunctionArguments
        {
            ["regexPattern"] = "Important",
        });

        // Assert — matches at every depth, returned as store-root-relative paths
        var entries = Assert.IsType<JsonElement>(result).EnumerateArray().ToList();
        var names = entries.ConvertAll(e => e.GetProperty("fileName").GetString());
        Assert.Equal(3, names.Count);
        Assert.Contains("root.md", names);
        Assert.Contains("reports/q1.md", names);
        Assert.Contains("reports/2024/q2.md", names);
    }

    [Fact]
    public async Task SearchFiles_GlobScopesToSubtreeAsync()
    {
        // Arrange
        var store = new InMemoryAgentFileStore();
        await store.WriteAsync("root.md", "Important data at root");
        await store.WriteAsync("reports/q1.md", "Important data in reports");
        await store.WriteAsync("reports/2024/q2.md", "Important data nested deeper");
        var tools = await CreateToolsAsync(store);
        var searchFiles = GetTool(tools, "file_access_grep");

        // Act — restrict to the reports subtree using a recursive glob
        var result = await InvokeToolAsync(searchFiles, new AIFunctionArguments
        {
            ["regexPattern"] = "Important",
            ["globPattern"] = "reports/**",
        });

        // Assert — only the files under reports/ match
        var entries = Assert.IsType<JsonElement>(result).EnumerateArray().ToList();
        var names = entries.ConvertAll(e => e.GetProperty("fileName").GetString());
        Assert.Equal(2, names.Count);
        Assert.Contains("reports/q1.md", names);
        Assert.Contains("reports/2024/q2.md", names);
    }

    [Fact]
    public async Task SearchFiles_RecursiveGlobMatchesNestedExtensionAsync()
    {
        // Arrange
        var store = new InMemoryAgentFileStore();
        await store.WriteAsync("notes.md", "Important data");
        await store.WriteAsync("data/raw.txt", "Important data");
        await store.WriteAsync("reports/2024/q1.md", "Important data");
        var tools = await CreateToolsAsync(store);
        var searchFiles = GetTool(tools, "file_access_grep");

        // Act — match markdown files at any depth
        var result = await InvokeToolAsync(searchFiles, new AIFunctionArguments
        {
            ["regexPattern"] = "Important",
            ["globPattern"] = "**/*.md",
        });

        // Assert
        var entries = Assert.IsType<JsonElement>(result).EnumerateArray().ToList();
        var names = entries.ConvertAll(e => e.GetProperty("fileName").GetString());
        Assert.Equal(2, names.Count);
        Assert.Contains("notes.md", names);
        Assert.Contains("reports/2024/q1.md", names);
    }

    #endregion

    #region Path Traversal Protection

    [Fact]
    public async Task SaveFile_PathTraversal_ThrowsAsync()
    {
        // Arrange
        var tools = await CreateToolsAsync();
        var saveFile = GetTool(tools, "file_access_write");

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
        var saveFile = GetTool(tools, "file_access_write");

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
        var saveFile = GetTool(tools, "file_access_write");

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
        var saveFile = GetTool(tools, "file_access_write");

        // Act
        await InvokeToolAsync(saveFile, new AIFunctionArguments
        {
            ["fileName"] = "notes..md",
            ["content"] = "Content",
        });

        // Assert
        Assert.Equal("Content", await store.ReadAsync("notes..md"));
    }

    [Fact]
    public async Task ReadFile_PathTraversal_ThrowsAsync()
    {
        // Arrange
        var tools = await CreateToolsAsync();
        var readFile = GetTool(tools, "file_access_read");

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
        var deleteFile = GetTool(tools, "file_access_delete");

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

    [Fact]
    public async Task Options_DisableWriteTools_OnlyExposesReadOnlyToolsAsync()
    {
        // Arrange
        var options = new FileAccessProviderOptions { DisableWriteTools = true };
        var provider = new FileAccessProvider(new InMemoryAgentFileStore(), options: options);
        var agent = new Mock<AIAgent>().Object;
        var session = new ChatClientAgentSession();
#pragma warning disable MAAI001
        var context = new AIContextProvider.InvokingContext(agent, session, new AIContext());
#pragma warning restore MAAI001

        // Act
        AIContext result = await provider.InvokingAsync(context);
        var names = result.Tools!.OfType<AIFunction>().Select(t => t.Name).ToList();

        // Assert — only read-only tools are exposed.
        Assert.Equal(3, names.Count);
        Assert.Contains(FileAccessProvider.ReadFileToolName, names);
        Assert.Contains(FileAccessProvider.LsToolName, names);
        Assert.Contains(FileAccessProvider.GrepToolName, names);
        Assert.DoesNotContain(FileAccessProvider.WriteToolName, names);
        Assert.DoesNotContain(FileAccessProvider.DeleteFileToolName, names);
        Assert.DoesNotContain(FileAccessProvider.ReplaceToolName, names);
        Assert.DoesNotContain(FileAccessProvider.ReplaceLinesToolName, names);
    }

    #endregion

    #region Replace Tests

    [Fact]
    public async Task Replace_SingleOccurrence_ReplacesAndReturnsCountAsync()
    {
        // Arrange
        var store = new InMemoryAgentFileStore();
        await store.WriteAsync("notes.md", "Hello world");
        var tools = await CreateToolsAsync(store);
        var replace = GetTool(tools, "file_access_replace");

        // Act
        var result = await InvokeToolAsync(replace, new AIFunctionArguments
        {
            ["fileName"] = "notes.md",
            ["oldString"] = "world",
            ["newString"] = "there",
        });

        // Assert
        var text = Assert.IsType<JsonElement>(result).GetString();
        Assert.Contains("Replaced 1 occurrence(s)", text);
        Assert.Equal("Hello there", await store.ReadAsync("notes.md"));
    }

    [Fact]
    public async Task Replace_MultipleOccurrences_WithoutReplaceAll_ThrowsAsync()
    {
        // Arrange
        var store = new InMemoryAgentFileStore();
        await store.WriteAsync("notes.md", "a a a");
        var tools = await CreateToolsAsync(store);
        var replace = GetTool(tools, "file_access_replace");

        // Act & Assert — exception bubbles, content unchanged
        await Assert.ThrowsAsync<ArgumentException>(async () =>
            await InvokeToolAsync(replace, new AIFunctionArguments
            {
                ["fileName"] = "notes.md",
                ["oldString"] = "a",
                ["newString"] = "b",
            }));
        Assert.Equal("a a a", await store.ReadAsync("notes.md"));
    }

    [Fact]
    public async Task Replace_ReplaceAll_ReplacesEveryOccurrenceAsync()
    {
        // Arrange
        var store = new InMemoryAgentFileStore();
        await store.WriteAsync("notes.md", "a a a");
        var tools = await CreateToolsAsync(store);
        var replace = GetTool(tools, "file_access_replace");

        // Act
        var result = await InvokeToolAsync(replace, new AIFunctionArguments
        {
            ["fileName"] = "notes.md",
            ["oldString"] = "a",
            ["newString"] = "b",
            ["replaceAll"] = true,
        });

        // Assert
        var text = Assert.IsType<JsonElement>(result).GetString();
        Assert.Contains("Replaced 3 occurrence(s)", text);
        Assert.Equal("b b b", await store.ReadAsync("notes.md"));
    }

    [Fact]
    public async Task Replace_NonExistentFile_ReturnsNotFoundAsync()
    {
        // Arrange
        var tools = await CreateToolsAsync();
        var replace = GetTool(tools, "file_access_replace");

        // Act
        var result = await InvokeToolAsync(replace, new AIFunctionArguments
        {
            ["fileName"] = "missing.md",
            ["oldString"] = "x",
            ["newString"] = "y",
        });

        // Assert
        var text = Assert.IsType<JsonElement>(result).GetString();
        Assert.Contains("not found", text);
    }

    #endregion

    #region ReplaceLines Tests

    [Fact]
    public async Task ReplaceLines_ReplacesSpecifiedLinesAsync()
    {
        // Arrange
        var store = new InMemoryAgentFileStore();
        await store.WriteAsync("notes.md", "line1\nline2\nline3");
        var tools = await CreateToolsAsync(store);
        var replaceLines = GetTool(tools, "file_access_replace_lines");

        // Act
        var result = await InvokeToolAsync(replaceLines, new AIFunctionArguments
        {
            ["fileName"] = "notes.md",
            ["edits"] = new List<FileLineEdit> { new() { LineNumber = 2, NewLine = "CHANGED\n" } },
        });

        // Assert
        var text = Assert.IsType<JsonElement>(result).GetString();
        Assert.Contains("Replaced 1 line(s)", text);
        Assert.Equal("line1\nCHANGED\nline3", await store.ReadAsync("notes.md"));
    }

    [Fact]
    public async Task ReplaceLines_OutOfRange_ThrowsAsync()
    {
        // Arrange
        var store = new InMemoryAgentFileStore();
        await store.WriteAsync("notes.md", "line1\nline2");
        var tools = await CreateToolsAsync(store);
        var replaceLines = GetTool(tools, "file_access_replace_lines");

        // Act & Assert — exception bubbles, content unchanged
        await Assert.ThrowsAsync<ArgumentException>(async () =>
            await InvokeToolAsync(replaceLines, new AIFunctionArguments
            {
                ["fileName"] = "notes.md",
                ["edits"] = new List<FileLineEdit> { new() { LineNumber = 5, NewLine = "X" } },
            }));
        Assert.Equal("line1\nline2", await store.ReadAsync("notes.md"));
    }

    #endregion

    #region Grep Directory Re-Root

    [Fact]
    public async Task Grep_WithDirectory_RerootsResultsToStoreRootAsync()
    {
        // Arrange
        var store = new InMemoryAgentFileStore();
        await store.WriteAsync("reports/q1.md", "Important data in reports");
        await store.WriteAsync("reports/2024/q2.md", "Important data nested deeper");
        var tools = await CreateToolsAsync(store);
        var grep = GetTool(tools, "file_access_grep");

        // Act — restrict the search to the reports directory.
        var result = await InvokeToolAsync(grep, new AIFunctionArguments
        {
            ["regexPattern"] = "Important",
            ["directory"] = "reports",
        });

        // Assert — results are returned as store-root-relative paths (prefixed with the directory).
        var entries = Assert.IsType<JsonElement>(result).EnumerateArray().ToList();
        var names = entries.ConvertAll(e => e.GetProperty("fileName").GetString());
        Assert.Equal(2, names.Count);
        Assert.Contains("reports/q1.md", names);
        Assert.Contains("reports/2024/q2.md", names);
    }

    #endregion

    #region Helper Methods

    private static async Task<IEnumerable<AITool>> CreateToolsAsync(InMemoryAgentFileStore? store = null)
        => await CreateToolsAsync(null, store);

    private static async Task<IEnumerable<AITool>> CreateToolsAsync(FileAccessProviderOptions? options, InMemoryAgentFileStore? store = null)
    {
        var provider = new FileAccessProvider(store ?? new InMemoryAgentFileStore(), options);
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
