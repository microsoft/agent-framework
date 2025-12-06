// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Runtime.CompilerServices;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Hosting.AGUI.AspNetCore.UnitTests;

internal static class TestHelpers
{
    /// <summary>
    /// Extension method to convert a synchronous enumerable to an async enumerable for testing purposes.
    /// </summary>
    public static async IAsyncEnumerable<T> ToAsyncEnumerableAsync<T>(this IEnumerable<T> source)
    {
        foreach (T item in source)
        {
            yield return item;
            await Task.CompletedTask;
        }
    }
}

/// <summary>
/// Simple mock implementation of IChatClient for basic testing purposes.
/// </summary>
internal sealed class SimpleMockChatClient : IChatClient
{
    private readonly string _responseText;

    public SimpleMockChatClient(string responseText = "Test response")
    {
        this._responseText = responseText;
    }

    public ChatClientMetadata Metadata { get; } = new("Test", new Uri("https://test.example.com"), "test-model");

    public Task<ChatResponse> GetResponseAsync(
        IEnumerable<ChatMessage> messages,
        ChatOptions? options = null,
        CancellationToken cancellationToken = default)
    {
        // Count input messages to simulate context size
        int messageCount = messages.Count();
        ChatMessage message = new(ChatRole.Assistant, this._responseText);
        ChatResponse response = new([message])
        {
            ModelId = "test-model",
            FinishReason = ChatFinishReason.Stop,
            Usage = new UsageDetails
            {
                InputTokenCount = 10 + (messageCount * 5),
                OutputTokenCount = 5,
                TotalTokenCount = 15 + (messageCount * 5)
            }
        };
        return Task.FromResult(response);
    }

    public async IAsyncEnumerable<ChatResponseUpdate> GetStreamingResponseAsync(
        IEnumerable<ChatMessage> messages,
        ChatOptions? options = null,
        [EnumeratorCancellation] CancellationToken cancellationToken = default)
    {
        await Task.Delay(1, cancellationToken);

        // Count input messages to simulate context size
        int messageCount = messages.Count();

        // Split response into words to simulate streaming
        string[] words = this._responseText.Split(' ');
        for (int i = 0; i < words.Length; i++)
        {
            string content = i < words.Length - 1 ? words[i] + " " : words[i];
            ChatResponseUpdate update = new()
            {
                Contents = [new TextContent(content)],
                Role = ChatRole.Assistant
            };

            // Add usage to the last update
            if (i == words.Length - 1)
            {
                update.Contents.Add(new UsageContent(new UsageDetails
                {
                    InputTokenCount = 10 + (messageCount * 5),
                    OutputTokenCount = 5,
                    TotalTokenCount = 15 + (messageCount * 5)
                }));
            }

            yield return update;
        }
    }

    public object? GetService(Type serviceType, object? serviceKey = null) =>
        serviceType.IsInstanceOfType(this) ? this : null;

    public void Dispose()
    {
    }
}
