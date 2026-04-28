// Copyright (c) Microsoft. All rights reserved.

// This sample demonstrates resumable streaming using ValkeyStreamBuffer.
// No LLM is required — it simulates agent response chunks to show the
// append, disconnect, and resume workflow backed by Valkey Streams.
//
// Prerequisites:
//   - Any Valkey or Redis OSS server (no modules required):
//       docker run -d --name valkey -p 6379:6379 valkey/valkey:latest

using Microsoft.Agents.AI;
using Microsoft.Agents.AI.Valkey;
using Microsoft.Extensions.AI;

var valkeyConnection = Environment.GetEnvironmentVariable("VALKEY_CONNECTION") ?? "localhost:6379";

// Simulate an agent response as a sequence of chunks
string[] simulatedChunks =
[
    "Valkey Streams provide a ",
    "powerful append-only log ",
    "data structure. ",
    "They support consumer groups ",
    "for distributed processing, ",
    "and each entry gets a unique ",
    "auto-generated ID that serves ",
    "as a natural continuation token. ",
    "This makes them ideal for ",
    "resumable streaming scenarios ",
    "in AI agent frameworks."
];

await using var streamBuffer = new ValkeyStreamBuffer(
    valkeyConnection,
    keyPrefix: "sample_stream")
{
    MaxLength = 1000
};

var responseId = $"response-{Guid.NewGuid():N}";

// ============================================================
// Part 1: Stream chunks, simulating a disconnect after 4
// ============================================================
Console.WriteLine("=== Part 1: Streaming with simulated disconnect ===\n");

string? lastEntryId = null;
int disconnectAfter = 4;

for (int i = 0; i < simulatedChunks.Length; i++)
{
    var update = new AgentResponseUpdate(ChatRole.Assistant, simulatedChunks[i]);
    lastEntryId = await streamBuffer.AppendAsync(responseId, update);

    Console.Write(simulatedChunks[i]);

    if (i + 1 >= disconnectAfter)
    {
        Console.ForegroundColor = ConsoleColor.Red;
        Console.WriteLine($"\n\n  ⚡ CLIENT DISCONNECTED after {disconnectAfter} chunks!");
        Console.ResetColor();
        break;
    }
}

// Meanwhile, the "server" keeps writing the remaining chunks
for (int i = disconnectAfter; i < simulatedChunks.Length; i++)
{
    var update = new AgentResponseUpdate(ChatRole.Assistant, simulatedChunks[i]);
    await streamBuffer.AppendAsync(responseId, update);
}

var totalStored = await streamBuffer.GetEntryCountAsync(responseId);
Console.WriteLine($"  📦 {totalStored} total chunks persisted in Valkey Stream.");
Console.WriteLine($"  🔖 Last seen entry ID: {lastEntryId}\n");

// ============================================================
// Part 2: Resume from the last-seen entry ID
// ============================================================
Console.WriteLine("=== Part 2: Resuming from last-seen entry ===\n");

Console.ForegroundColor = ConsoleColor.Green;
Console.WriteLine("  🔄 Replaying missed chunks from Valkey...\n");
Console.ResetColor();

int resumedCount = 0;
await foreach (var (entryId, update) in streamBuffer.ReadAsync(responseId, afterEntryId: lastEntryId!))
{
    Console.Write(update.Text);
    resumedCount++;
}

Console.WriteLine($"\n\n  ✅ Resumed {resumedCount} missed chunks.");

// ============================================================
// Part 3: Full replay from the beginning
// ============================================================
Console.WriteLine("\n=== Part 3: Full replay from beginning ===\n");

int fullCount = 0;
await foreach (var (entryId, update) in streamBuffer.ReadAsync(responseId))
{
    Console.Write(update.Text);
    fullCount++;
}

Console.WriteLine($"\n\n  📊 Full replay: {fullCount} total chunks.");

// Cleanup
await streamBuffer.DeleteStreamAsync(responseId);
Console.WriteLine("  🗑️  Stream deleted.\n");
Console.WriteLine("Done!");
