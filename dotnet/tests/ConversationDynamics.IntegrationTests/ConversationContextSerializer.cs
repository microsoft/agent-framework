// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.IO;
using System.Text.Json;
using Microsoft.Agents.AI;
using Microsoft.Extensions.AI;

namespace ConversationDynamics.IntegrationTests;

/// <summary>
/// Provides helpers for serializing and deserializing conversation contexts (lists of <see cref="ChatMessage"/>)
/// to and from JSON, enabling the initial context of a test case to be captured once and reused across runs.
/// </summary>
public static class ConversationContextSerializer
{
    private static readonly JsonSerializerOptions s_serializerOptions = AgentAbstractionsJsonUtilities.DefaultOptions;

    /// <summary>
    /// Serializes a list of <see cref="ChatMessage"/> instances to a JSON string.
    /// </summary>
    /// <param name="messages">The messages to serialize.</param>
    /// <returns>A JSON string representation of the messages.</returns>
    public static string Serialize(IList<ChatMessage> messages) =>
        JsonSerializer.Serialize(messages, s_serializerOptions);

    /// <summary>
    /// Deserializes a JSON string into a list of <see cref="ChatMessage"/> instances.
    /// </summary>
    /// <param name="json">The JSON string to deserialize.</param>
    /// <returns>The deserialized list of messages.</returns>
    /// <exception cref="InvalidOperationException">
    /// Thrown when the JSON cannot be deserialized into a list of <see cref="ChatMessage"/> instances.
    /// </exception>
    public static IList<ChatMessage> Deserialize(string json)
    {
        var messages = JsonSerializer.Deserialize<List<ChatMessage>>(json, s_serializerOptions);
        return messages ?? throw new InvalidOperationException("Failed to deserialize chat messages from the provided JSON.");
    }

    /// <summary>
    /// Saves a list of <see cref="ChatMessage"/> instances to a JSON file.
    /// </summary>
    /// <param name="filePath">The path of the file to write.</param>
    /// <param name="messages">The messages to save.</param>
    public static void SaveToFile(string filePath, IList<ChatMessage> messages)
    {
        var json = Serialize(messages);
        File.WriteAllText(filePath, json);
    }

    /// <summary>
    /// Loads a list of <see cref="ChatMessage"/> instances from a JSON file.
    /// </summary>
    /// <param name="filePath">The path of the file to read.</param>
    /// <returns>The deserialized list of messages.</returns>
    /// <exception cref="FileNotFoundException">Thrown when <paramref name="filePath"/> does not exist.</exception>
    public static IList<ChatMessage> LoadFromFile(string filePath)
    {
        if (!File.Exists(filePath))
        {
            throw new FileNotFoundException($"Conversation context file not found: '{filePath}'. " +
                "Run the context creation step first to generate this file.", filePath);
        }

        var json = File.ReadAllText(filePath);
        return Deserialize(json);
    }
}
