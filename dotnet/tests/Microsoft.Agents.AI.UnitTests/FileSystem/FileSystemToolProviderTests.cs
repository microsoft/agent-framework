// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Runtime.InteropServices;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using Moq;

namespace Microsoft.Agents.AI.UnitTests.FileSystem;

public sealed class FileSystemToolProviderTests : IDisposable
{
    private readonly string _root;

    public FileSystemToolProviderTests()
    {
        this._root = Path.Combine(Path.GetTempPath(), "filesystem-tool-provider-tests-" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(this._root);
    }

    public void Dispose()
    {
        if (Directory.Exists(this._root))
        {
            try
            {
                Directory.Delete(this._root, recursive: true);
            }
            catch (IOException)
            {
                // Best-effort cleanup; symlink test directories may already be gone.
            }
        }
    }

    [Fact]
    public void Provider_IsAFileAccessProvider()
    {
        var provider = new FileSystemToolProvider(this._root);
        FileAccessProvider basePolymorphic = provider;

        Assert.NotNull(basePolymorphic);
        Assert.Equal(this._root, provider.Root, ignoreCase: !IsCaseSensitiveFs());
    }

    [Fact]
    public void Provider_CreatesRootIfMissing()
    {
        string fresh = Path.Combine(Path.GetTempPath(), "fsp-fresh-" + Guid.NewGuid().ToString("N"));
        try
        {
            Assert.False(Directory.Exists(fresh));
            _ = new FileSystemToolProvider(fresh);
            Assert.True(Directory.Exists(fresh));
        }
        finally
        {
            if (Directory.Exists(fresh)) { Directory.Delete(fresh, recursive: true); }
        }
    }

    [Fact]
    public async Task ToolSurface_ContainsUniversalAndRichToolsAsync()
    {
        var tools = await this.GetToolsAsync();

        var names = tools.OfType<AIFunction>().Select(t => t.Name).ToHashSet();

        Assert.Contains("FileAccess_SaveFile", names);
        Assert.Contains("FileAccess_ReadFile", names);
        Assert.Contains("FileAccess_DeleteFile", names);
        Assert.Contains("FileAccess_ListFiles", names);
        Assert.Contains("FileAccess_SearchFiles", names);

        Assert.Contains("fs_view", names);
        Assert.Contains("fs_edit", names);
        Assert.Contains("fs_multi_edit", names);
        Assert.Contains("fs_glob", names);
        Assert.Contains("fs_grep", names);
        Assert.Contains("fs_list_dir", names);
        Assert.Contains("fs_move", names);
        Assert.Contains("fs_rename", names);

        Assert.DoesNotContain("fs_create", names);
        Assert.DoesNotContain("fs_delete", names);
    }

    [Fact]
    public async Task DestructiveTools_AreApprovalGatedAsync()
    {
        var tools = (await this.GetToolsAsync()).ToList();

        Assert.IsType<ApprovalRequiredAIFunction>(GetTool(tools, "FileAccess_DeleteFile"));
        Assert.IsType<ApprovalRequiredAIFunction>(GetTool(tools, "fs_move"));
        Assert.IsType<ApprovalRequiredAIFunction>(GetTool(tools, "fs_rename"));

        Assert.IsNotType<ApprovalRequiredAIFunction>(GetTool(tools, "FileAccess_SaveFile"));
        Assert.IsNotType<ApprovalRequiredAIFunction>(GetTool(tools, "fs_view"));
    }

    [Fact]
    public async Task DefaultInstructions_DescribeBothToolSurfacesAsync()
    {
        var instructions = await this.GetInstructionsAsync(new FileSystemToolProvider(this._root));

        Assert.NotNull(instructions);
        Assert.Contains("FileAccess_", instructions, StringComparison.Ordinal);
        Assert.Contains("fs_", instructions, StringComparison.Ordinal);
    }

    [Fact]
    public async Task CustomInstructions_OverrideDefaultsAsync()
    {
        var provider = new FileSystemToolProvider(this._root, new FileSystemToolProviderOptions
        {
            Instructions = "CUSTOM PROVIDER PROMPT",
        });

        Assert.Equal("CUSTOM PROVIDER PROMPT", await this.GetInstructionsAsync(provider));
    }

    [Fact]
    public async Task UniversalTools_BlockTraversalAsync()
    {
        var tools = await this.GetToolsAsync();
        var save = (AIFunction)GetTool(tools.ToList(), "FileAccess_SaveFile");

        await Assert.ThrowsAnyAsync<Exception>(async () =>
            await save.InvokeAsync(new AIFunctionArguments
            {
                ["fileName"] = "../escape.txt",
                ["content"] = "x",
                ["overwrite"] = true,
            }));
    }

    [Fact]
    public async Task UniversalTools_BlockSecretsByDefaultAsync()
    {
        var tools = await this.GetToolsAsync();
        var save = (AIFunction)GetTool(tools.ToList(), "FileAccess_SaveFile");

        await Assert.ThrowsAnyAsync<Exception>(async () =>
            await save.InvokeAsync(new AIFunctionArguments
            {
                ["fileName"] = ".env.local",
                ["content"] = "SECRET=x",
                ["overwrite"] = true,
            }));
    }

    [Fact]
    public async Task RichTool_View_HonorsLineRangeAsync()
    {
        File.WriteAllText(Path.Combine(this._root, "src.txt"), "a\nb\nc\nd\ne\n");

        var tools = await this.GetToolsAsync();
        var view = (AIFunction)GetTool(tools.ToList(), "fs_view");

        var result = await view.InvokeAsync(new AIFunctionArguments
        {
            ["path"] = "src.txt",
            ["startLine"] = 2,
            ["endLine"] = 4,
        });

        Assert.NotNull(result);
        string text = result!.ToString()!;
        Assert.Contains("b", text, StringComparison.Ordinal);
        Assert.Contains("c", text, StringComparison.Ordinal);
        Assert.Contains("d", text, StringComparison.Ordinal);
    }

    private async Task<IEnumerable<AITool>> GetToolsAsync()
    {
        var provider = new FileSystemToolProvider(this._root);
        var agent = new Mock<AIAgent>().Object;
        var session = new ChatClientAgentSession();
#pragma warning disable MAAI001
        var context = new AIContextProvider.InvokingContext(agent, session, new AIContext());
#pragma warning restore MAAI001
        AIContext result = await provider.InvokingAsync(context);
        return result.Tools!;
    }

    private async Task<string?> GetInstructionsAsync(FileSystemToolProvider provider)
    {
        var agent = new Mock<AIAgent>().Object;
        var session = new ChatClientAgentSession();
#pragma warning disable MAAI001
        var context = new AIContextProvider.InvokingContext(agent, session, new AIContext());
#pragma warning restore MAAI001
        AIContext result = await provider.InvokingAsync(context);
        return result.Instructions;
    }

    private static AITool GetTool(IList<AITool> tools, string name)
    {
        var match = tools.FirstOrDefault(t => t is AIFunction f && f.Name == name);
        Assert.NotNull(match);
        return match!;
    }

    private static bool IsCaseSensitiveFs() =>
        Environment.OSVersion.Platform == PlatformID.Unix &&
        !RuntimeInformation.IsOSPlatform(OSPlatform.OSX);
}
