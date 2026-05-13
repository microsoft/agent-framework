// Copyright (c) Microsoft. All rights reserved.

using System;
using System.IO;
using System.Text.Json;
using System.Threading.Tasks;
using FluentAssertions;

namespace Microsoft.Agents.AI.Workflows.UnitTests;

public sealed class PrimitiveCheckpointEncodingContractTests
{
    [Fact]
    public async Task PrimitiveCheckpointFixture_RoundTripsThroughJsonCheckpointStoreAsync()
    {
        JsonElement fixture = LoadFixture();
        InMemoryJsonStore store = new();

        CheckpointInfo checkpoint = await store.CreateCheckpointAsync("session-1", fixture);
        JsonElement restored = await store.RetrieveCheckpointAsync("session-1", checkpoint);

        restored.GetRawText().Should().Be(fixture.GetRawText());
        restored.GetProperty("string").GetString().Should().Be("hello");
        restored.GetProperty("integer").GetInt32().Should().Be(42);
        restored.GetProperty("float").GetDouble().Should().Be(3.5d);
        restored.GetProperty("boolean").GetBoolean().Should().BeTrue();
        restored.GetProperty("nullValue").ValueKind.Should().Be(JsonValueKind.Null);
    }

    private static JsonElement LoadFixture()
    {
        string current = AppContext.BaseDirectory;
        while (!string.IsNullOrEmpty(current))
        {
            string candidate = Path.Combine(current, "testdata", "checkpoint_primitive_contract.json");
            if (File.Exists(candidate))
            {
                using JsonDocument document = JsonDocument.Parse(File.ReadAllText(candidate));
                return document.RootElement.Clone();
            }

            DirectoryInfo? parent = Directory.GetParent(current);
            if (parent is null)
            {
                break;
            }

            current = parent.FullName;
        }

        throw new InvalidOperationException("checkpoint primitive contract fixture not found");
    }
}
