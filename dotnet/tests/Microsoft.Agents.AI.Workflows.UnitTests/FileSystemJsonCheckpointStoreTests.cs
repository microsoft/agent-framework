// Copyright (c) Microsoft. All rights reserved.

using System;
using System.IO;
using System.Text.Json;
using System.Threading.Tasks;
using FluentAssertions;
using Microsoft.Agents.AI.Workflows.Checkpointing;

namespace Microsoft.Agents.AI.Workflows.UnitTests;

internal sealed class TempDirectory : IDisposable
{
    public DirectoryInfo DirectoryInfo { get; }

    public TempDirectory()
    {
        string tempDirPath = Path.Combine(Path.GetTempPath(), Guid.NewGuid().ToString());
        this.DirectoryInfo = Directory.CreateDirectory(tempDirPath);
    }

    public void Dispose()
    {
        this.DisposeInternal();
        GC.SuppressFinalize(this);
    }

    private void DisposeInternal()
    {
        if (this.DirectoryInfo.Exists)
        {
            try
            {
                // Best efforts
                this.DirectoryInfo.Delete(recursive: true);
            }
            catch { }
        }
    }

    ~TempDirectory()
    {
        // Best efforts
        this.DisposeInternal();
    }

    public static implicit operator DirectoryInfo(TempDirectory tempDirectory) => tempDirectory.DirectoryInfo;

    public string FullName => this.DirectoryInfo.FullName;

    public bool IsParentOf(FileInfo candidate)
    {
        if (candidate.Directory is null)
        {
            return false;
        }

        if (candidate.Directory.FullName == this.DirectoryInfo.FullName)
        {
            return true;
        }

        return this.IsParentOf(candidate.Directory);
    }

    public bool IsParentOf(DirectoryInfo candidate)
    {
        while (candidate.Parent is not null)
        {
            if (candidate.Parent.FullName == this.DirectoryInfo.FullName)
            {
                return true;
            }

            candidate = candidate.Parent;
        }

        return false;
    }
}
public sealed class FileSystemJsonCheckpointStoreTests
{
    public static JsonElement TestData => JsonSerializer.SerializeToElement(new { test = "data" });

    [Fact]
    public async Task CreateCheckpointAsync_ShouldPersistIndexToDiskBeforeDisposeAsync()
    {
        // Arrange
        using TempDirectory tempDirectory = new();
        using FileSystemJsonCheckpointStore? store = new(tempDirectory);

        string runId = Guid.NewGuid().ToString("N");

        // Act
        CheckpointInfo checkpoint = await store.CreateCheckpointAsync(runId, TestData);

        // Assert - Check the file size before disposing to verify data was flushed to disk
        // The index.jsonl file is held exclusively by the store, so we check via FileInfo
        string indexPath = Path.Combine(tempDirectory.FullName, "index.jsonl");
        FileInfo indexFile = new(indexPath);
        indexFile.Refresh();
        long fileSizeBeforeDispose = indexFile.Length;

        // Data should already be on disk (file size > 0) before we dispose
        fileSizeBeforeDispose.Should().BeGreaterThan(0, "index.jsonl should be flushed to disk after CreateCheckpointAsync");

        // Dispose to release file lock before final verification
        store.Dispose();

        string[] lines = File.ReadAllLines(indexPath);
        lines.Should().HaveCount(1);
        lines[0].Should().Contain(checkpoint.CheckpointId);
    }

    private async ValueTask Run_EscapeRootFolderTestAsync(string escapingPath)
    {
        // Arrange
        using TempDirectory tempDirectory = new();
        using FileSystemJsonCheckpointStore store = new(tempDirectory);

        string naivePath = Path.Combine(tempDirectory.DirectoryInfo.FullName, escapingPath);

        // Check that the naive path is actually outside the temp directory to validate the test is meaningful
        FileInfo naiveCheckpointFile = new(naivePath);
        tempDirectory.IsParentOf(naiveCheckpointFile).Should().BeFalse("The naive path should be outside the root folder to validate that escaping is necessary.");

        // Act
        CheckpointInfo checkpointInfo = await store.CreateCheckpointAsync(escapingPath, TestData);

        // Assert
        string naivePathWithCheckpointId = Path.Combine(tempDirectory.DirectoryInfo.FullName, $"{escapingPath}_{checkpointInfo.CheckpointId}.json");
        new FileInfo(naivePathWithCheckpointId).Exists.Should().BeFalse("The naive path should not be used to save a checkpoint file.");

        string actualFileName = store.GetFileNameForCheckpoint(escapingPath, checkpointInfo);
        string actualFilePath = Path.Combine(tempDirectory.DirectoryInfo.FullName, actualFileName);
        FileInfo actualFile = new(actualFilePath);

        tempDirectory.IsParentOf(actualFile).Should().BeTrue("The actual checkpoint should be saved inside the root folder.");
        actualFile.Exists.Should().BeTrue("The actual path should be used to save a checkpoint file.");
    }

    [Fact]
    public async Task CreateCheckpointAsync_ShouldNotEscapeRootFolderAsync()
    {
        // The SessionId is used as part of the file name, but if it contains path characters such as /.. it can escape the root folder.
        // Testing that such characters are escaped properly to prevent directory traversal attacks, etc.

        await this.Run_EscapeRootFolderTestAsync("../valid_suffix");

#if !NETFRAMEWORK
        if (OperatingSystem.IsWindows())
        {
            // Windows allows both \ and / as path separators, so we test both
            await this.Run_EscapeRootFolderTestAsync("..\\valid_suffix");
        }
#else
        // .NET Framework is always on Windows
        await this.Run_EscapeRootFolderTestAsync("..\\valid_suffix");
#endif
    }

    private const string InvalidPathCharsWin32 = "\\/:*?\"<>|";
    private const string InvalidPathCharsUnix = "/";
    private const string InvalidPathCharsMacOS = "/:";

    [Theory]
    [InlineData(InvalidPathCharsWin32)]
    [InlineData(InvalidPathCharsUnix)]
    [InlineData(InvalidPathCharsMacOS)]
    public async Task CreateCheckpointAsync_EscapesInvalidCharsAsync(string invalidChars)
    {
        // Arrange
        using TempDirectory tempDirectory = new();
        using FileSystemJsonCheckpointStore store = new(tempDirectory);

        string runId = $"prefix_{invalidChars}_suffix";

        Func<Task> createCheckpointAction = async () => await store.CreateCheckpointAsync(runId, TestData);
        await createCheckpointAction.Should().NotThrowAsync();
    }

    [Fact]
    public async Task RetrieveCheckpointAsync_ShouldReturnPersistedDataAsync()
    {
        // Arrange
        using TempDirectory tempDirectory = new();
        using FileSystemJsonCheckpointStore store = new(tempDirectory);

        string sessionId = Guid.NewGuid().ToString("N");
        JsonElement originalData = JsonSerializer.SerializeToElement(new { name = "test", value = 42 });

        // Act
        CheckpointInfo checkpoint = await store.CreateCheckpointAsync(sessionId, originalData);
        JsonElement retrieved = await store.RetrieveCheckpointAsync(sessionId, checkpoint);

        // Assert
        retrieved.GetProperty("name").GetString().Should().Be("test");
        retrieved.GetProperty("value").GetInt32().Should().Be(42);
    }
}
