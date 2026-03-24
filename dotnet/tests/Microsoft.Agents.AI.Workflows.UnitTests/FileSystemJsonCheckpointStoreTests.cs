// Copyright (c) Microsoft. All rights reserved.

using System;
using System.IO;
using System.Text.Json;
using System.Threading.Tasks;
using FluentAssertions;
using Microsoft.Agents.AI.Workflows.Checkpointing;

namespace Microsoft.Agents.AI.Workflows.UnitTests;

public sealed class FileSystemJsonCheckpointStoreTests
{
    [Fact]
    public async Task CreateCheckpointAsync_ShouldPersistIndexToDiskBeforeDisposeAsync()
    {
        // Arrange
        DirectoryInfo tempDir = new(Path.Combine(Path.GetTempPath(), Guid.NewGuid().ToString()));
        FileSystemJsonCheckpointStore? store = null;

        try
        {
            store = new(tempDir);
            string runId = Guid.NewGuid().ToString("N");
            JsonElement testData = JsonSerializer.SerializeToElement(new { test = "data" });

            // Act
            CheckpointInfo checkpoint = await store.CreateCheckpointAsync(runId, testData);

            // Assert - Check the file size before disposing to verify data was flushed to disk
            // The index.jsonl file is held exclusively by the store, so we check via FileInfo
            string indexPath = Path.Combine(tempDir.FullName, "index.jsonl");
            FileInfo indexFile = new(indexPath);
            indexFile.Refresh();
            long fileSizeBeforeDispose = indexFile.Length;

            // Data should already be on disk (file size > 0) before we dispose
            fileSizeBeforeDispose.Should().BeGreaterThan(0, "index.jsonl should be flushed to disk after CreateCheckpointAsync");

            // Dispose to release file lock before final verification
            store.Dispose();
            store = null;

            string[] lines = File.ReadAllLines(indexPath);
            lines.Should().HaveCount(1);
            lines[0].Should().Contain(checkpoint.CheckpointId);
        }
        finally
        {
            store?.Dispose();
            if (tempDir.Exists)
            {
                tempDir.Delete(recursive: true);
            }
        }
    }
}
