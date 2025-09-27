// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json;

namespace Microsoft.Agents.AI.Runtime.Samples;

/// <summary>
/// Example demonstrating how to use the InMemoryActorStateStorage.
/// </summary>
public static class InMemoryActorStateStorageExample
{
    /// <summary>
    /// Demonstrates the basic usage of InMemoryActorStateStorage.
    /// </summary>
    /// <returns>A task representing the asynchronous operation.</returns>
    public static async Task RunAsync()
    {
        // Create an in-memory actor state storage
        var storage = new InMemoryActorStateStorage();

        // Create an actor ID
        var actorId = new ActorId("ExampleActor", "instance1");

        Console.WriteLine("=== InMemoryActorStateStorage Example ===");
        Console.WriteLine();

        // 1. Write some initial state
        Console.WriteLine("1. Writing initial state...");
        var initialOperations = new List<ActorStateWriteOperation>
        {
            new SetValueOperation("name", JsonSerializer.SerializeToElement("John Doe")),
            new SetValueOperation("age", JsonSerializer.SerializeToElement(30)),
            new SetValueOperation("city", JsonSerializer.SerializeToElement("Seattle"))
        };

        var writeResult = await storage.WriteStateAsync(actorId, initialOperations, "0").ConfigureAwait(false);
        Console.WriteLine($"   Write successful: {writeResult.Success}");
        Console.WriteLine($"   New ETag: {writeResult.ETag}");
        Console.WriteLine($"   Actor count: {storage.ActorCount}");
        Console.WriteLine($"   Key count for actor: {storage.GetKeyCount(actorId)}");
        Console.WriteLine();

        // 2. Read the state back
        Console.WriteLine("2. Reading state back...");
        var readOperations = new List<ActorStateReadOperation>
        {
            new GetValueOperation("name"),
            new GetValueOperation("age"),
            new GetValueOperation("city"),
            new GetValueOperation("nonexistent"), // This won't exist
            new ListKeysOperation(continuationToken: null) // List all keys
        };

        var readResult = await storage.ReadStateAsync(actorId, readOperations).ConfigureAwait(false);
        Console.WriteLine($"   Current ETag: {readResult.ETag}");
        Console.WriteLine("   Results:");

        foreach (var result in readResult.Results)
        {
            switch (result)
            {
                case GetValueResult getValue:
                    Console.WriteLine($"     - Get value: {getValue.Value?.ToString() ?? "null"}");
                    break;

                case ListKeysResult listKeys:
                    Console.WriteLine($"     - Keys: [{string.Join(", ", listKeys.Keys)}]");
                    break;
            }
        }
        Console.WriteLine();

        // 3. Update some values
        Console.WriteLine("3. Updating state...");
        var updateOperations = new List<ActorStateWriteOperation>
        {
            new SetValueOperation("age", JsonSerializer.SerializeToElement(31)), // Update age
            new SetValueOperation("email", JsonSerializer.SerializeToElement("john@example.com")), // Add email
            new RemoveKeyOperation("city") // Remove city
        };

        var updateResult = await storage.WriteStateAsync(actorId, updateOperations, writeResult.ETag).ConfigureAwait(false);
        Console.WriteLine($"   Update successful: {updateResult.Success}");
        Console.WriteLine($"   New ETag: {updateResult.ETag}");
        Console.WriteLine($"   Key count for actor: {storage.GetKeyCount(actorId)}");
        Console.WriteLine();

        // 4. Try to update with wrong ETag (should fail)
        Console.WriteLine("4. Trying to update with wrong ETag...");
        var failingOperations = new List<ActorStateWriteOperation>
        {
            new SetValueOperation("shouldFail", JsonSerializer.SerializeToElement("this should fail"))
        };

        var failResult = await storage.WriteStateAsync(actorId, failingOperations, "wrong-etag").ConfigureAwait(false);
        Console.WriteLine($"   Update successful: {failResult.Success}");
        Console.WriteLine($"   Current ETag: {failResult.ETag}");
        Console.WriteLine();

        // 5. Read final state
        Console.WriteLine("5. Reading final state...");
        var finalReadOperations = new List<ActorStateReadOperation>
        {
            new ListKeysOperation(continuationToken: null)
        };

        var finalReadResult = await storage.ReadStateAsync(actorId, finalReadOperations).ConfigureAwait(false);
        var finalKeys = finalReadResult.Results.OfType<ListKeysResult>().First();
        Console.WriteLine($"   Final keys: [{string.Join(", ", finalKeys.Keys)}]");

        // 6. Read each value
        foreach (var key in finalKeys.Keys)
        {
            var valueReadOperations = new List<ActorStateReadOperation>
            {
                new GetValueOperation(key)
            };

            var valueReadResult = await storage.ReadStateAsync(actorId, valueReadOperations).ConfigureAwait(false);
            var getValue = valueReadResult.Results.OfType<GetValueResult>().First();
            Console.WriteLine($"   - {key}: {getValue.Value}");
        }

        Console.WriteLine();
        Console.WriteLine("=== Example Complete ===");
    }
}
