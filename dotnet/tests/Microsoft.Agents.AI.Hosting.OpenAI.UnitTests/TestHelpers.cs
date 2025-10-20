// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Runtime.CompilerServices;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Hosting.OpenAI.UnitTests;

internal static class TestHelpers
{
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
                    InputTokenCount = 10 + (messageCount * 5),  // More messages = more tokens
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

    /// <summary>
    /// Mock implementation of IChatClient that returns responses with image content.
    /// </summary>
    internal sealed class ImageContentMockChatClient : IChatClient
    {
        private readonly string _imageUrl;

        public ImageContentMockChatClient(string imageUrl = "https://example.com/image.png")
        {
            this._imageUrl = imageUrl;
        }

        public ChatClientMetadata Metadata { get; } = new("Test", new Uri("https://test.example.com"), "test-model");

        public Task<ChatResponse> GetResponseAsync(
            IEnumerable<ChatMessage> messages,
            ChatOptions? options = null,
            CancellationToken cancellationToken = default)
        {
            ChatMessage message = new(ChatRole.Assistant, [
                new TextContent("Here is an image:"),
                new UriContent(this._imageUrl, "image/png")
            ]);
            ChatResponse response = new([message])
            {
                ModelId = "test-model",
                FinishReason = ChatFinishReason.Stop,
                Usage = new UsageDetails
                {
                    InputTokenCount = 10,
                    OutputTokenCount = 5,
                    TotalTokenCount = 15
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

            yield return new ChatResponseUpdate
            {
                Contents = [new TextContent("Here is an image:")],
                Role = ChatRole.Assistant
            };

            yield return new ChatResponseUpdate
            {
                Contents = [
                    new UriContent(this._imageUrl, "image/png"),
                    new UsageContent(new UsageDetails
                    {
                        InputTokenCount = 10,
                        OutputTokenCount = 5,
                        TotalTokenCount = 15
                    })
                ],
                Role = ChatRole.Assistant
            };
        }

        public object? GetService(Type serviceType, object? serviceKey = null) =>
            serviceType.IsInstanceOfType(this) ? this : null;

        public void Dispose()
        {
        }
    }

    /// <summary>
    /// Mock implementation of IChatClient that returns responses with audio content.
    /// </summary>
    internal sealed class AudioContentMockChatClient : IChatClient
    {
        private readonly byte[] _audioData;
        private readonly string _transcript;

        public AudioContentMockChatClient(string audioData = "base64audiodata", string transcript = "This is a transcript")
        {
            this._audioData = System.Text.Encoding.UTF8.GetBytes(audioData);
            this._transcript = transcript;
        }

        public ChatClientMetadata Metadata { get; } = new("Test", new Uri("https://test.example.com"), "test-model");

        public Task<ChatResponse> GetResponseAsync(
            IEnumerable<ChatMessage> messages,
            ChatOptions? options = null,
            CancellationToken cancellationToken = default)
        {
            ChatMessage message = new(ChatRole.Assistant, [
                new DataContent(this._audioData, "audio/wav")
                {
                    AdditionalProperties = new AdditionalPropertiesDictionary
                    {
                        ["transcript"] = this._transcript
                    }
                }
            ]);
            ChatResponse response = new([message])
            {
                ModelId = "test-model",
                FinishReason = ChatFinishReason.Stop,
                Usage = new UsageDetails
                {
                    InputTokenCount = 10,
                    OutputTokenCount = 5,
                    TotalTokenCount = 15
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

            yield return new ChatResponseUpdate
            {
                Contents = [
                    new DataContent(this._audioData, "audio/wav")
                    {
                        AdditionalProperties = new AdditionalPropertiesDictionary
                        {
                            ["transcript"] = this._transcript
                        }
                    },
                    new UsageContent(new UsageDetails
                    {
                        InputTokenCount = 10,
                        OutputTokenCount = 5,
                        TotalTokenCount = 15
                    })
                ],
                Role = ChatRole.Assistant
            };
        }

        public object? GetService(Type serviceType, object? serviceKey = null) =>
            serviceType.IsInstanceOfType(this) ? this : null;

        public void Dispose()
        {
        }
    }

    /// <summary>
    /// Mock implementation of IChatClient that returns responses with function calls.
    /// </summary>
    internal sealed class FunctionCallMockChatClient : IChatClient
    {
        private readonly string _functionName;
        private readonly Dictionary<string, object?> _arguments;

        public FunctionCallMockChatClient(string functionName = "test_function", string arguments = "{\"param\":\"value\"}")
        {
            this._functionName = functionName;
            this._arguments = System.Text.Json.JsonSerializer.Deserialize<Dictionary<string, object?>>(arguments) ?? new Dictionary<string, object?>();
        }

        public ChatClientMetadata Metadata { get; } = new("Test", new Uri("https://test.example.com"), "test-model");

        public Task<ChatResponse> GetResponseAsync(
            IEnumerable<ChatMessage> messages,
            ChatOptions? options = null,
            CancellationToken cancellationToken = default)
        {
            ChatMessage message = new(ChatRole.Assistant, [
                new FunctionCallContent("call_123", this._functionName)
                {
                    Arguments = this._arguments
                }
            ]);
            ChatResponse response = new([message])
            {
                ModelId = "test-model",
                FinishReason = ChatFinishReason.ToolCalls,
                Usage = new UsageDetails
                {
                    InputTokenCount = 80,
                    OutputTokenCount = 25,
                    TotalTokenCount = 105
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

            yield return new ChatResponseUpdate
            {
                Contents = [
                    new FunctionCallContent("call_123", this._functionName)
                    {
                        Arguments = this._arguments
                    },
                    new UsageContent(new UsageDetails
                    {
                        InputTokenCount = 80,
                        OutputTokenCount = 25,
                        TotalTokenCount = 105
                    })
                ],
                Role = ChatRole.Assistant
            };
        }

        public object? GetService(Type serviceType, object? serviceKey = null) =>
            serviceType.IsInstanceOfType(this) ? this : null;

        public void Dispose()
        {
        }
    }

    /// <summary>
    /// Mock implementation of IChatClient that returns mixed content types.
    /// </summary>
    internal sealed class MixedContentMockChatClient : IChatClient
    {
        public ChatClientMetadata Metadata { get; } = new("Test", new Uri("https://test.example.com"), "test-model");

        public Task<ChatResponse> GetResponseAsync(
            IEnumerable<ChatMessage> messages,
            ChatOptions? options = null,
            CancellationToken cancellationToken = default)
        {
            ChatMessage message = new(ChatRole.Assistant, [
                new TextContent("Here are multiple content types:"),
                new UriContent("https://example.com/image.png", "image/png"),
                new TextContent("And some more text after the image.")
            ]);
            ChatResponse response = new([message])
            {
                ModelId = "test-model",
                FinishReason = ChatFinishReason.Stop,
                Usage = new UsageDetails
                {
                    InputTokenCount = 10,
                    OutputTokenCount = 5,
                    TotalTokenCount = 15
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

            yield return new ChatResponseUpdate
            {
                Contents = [new TextContent("Here"), new TextContent(" are"), new TextContent(" multiple")],
                Role = ChatRole.Assistant
            };

            yield return new ChatResponseUpdate
            {
                Contents = [new TextContent(" content"), new TextContent(" types:")],
                Role = ChatRole.Assistant
            };

            yield return new ChatResponseUpdate
            {
                Contents = [new UriContent("https://example.com/image.png", "image/png")],
                Role = ChatRole.Assistant
            };

            yield return new ChatResponseUpdate
            {
                Contents = [new TextContent("And"), new TextContent(" some"), new TextContent(" more")],
                Role = ChatRole.Assistant
            };

            yield return new ChatResponseUpdate
            {
                Contents = [
                    new TextContent(" text"),
                    new TextContent(" after"),
                    new TextContent(" the"),
                    new TextContent(" image."),
                    new UsageContent(new UsageDetails
                    {
                        InputTokenCount = 10,
                        OutputTokenCount = 5,
                        TotalTokenCount = 15
                    })
                ],
                Role = ChatRole.Assistant
            };
        }

        public object? GetService(Type serviceType, object? serviceKey = null) =>
            serviceType.IsInstanceOfType(this) ? this : null;

        public void Dispose()
        {
        }
    }

    /// <summary>
    /// Mock implementation of IChatClient that returns custom content based on a provider function.
    /// </summary>
    internal sealed class CustomContentMockChatClient : IChatClient
    {
        private readonly Func<ChatMessage, IEnumerable<AIContent>> _contentProvider;

        public CustomContentMockChatClient(Func<ChatMessage, IEnumerable<AIContent>> contentProvider)
        {
            this._contentProvider = contentProvider;
        }

        public ChatClientMetadata Metadata { get; } = new("Test", new Uri("https://test.example.com"), "test-model");

        public Task<ChatResponse> GetResponseAsync(
            IEnumerable<ChatMessage> messages,
            ChatOptions? options = null,
            CancellationToken cancellationToken = default)
        {
            ChatMessage lastMessage = messages.Last();
            IEnumerable<AIContent> contents = this._contentProvider(lastMessage);
            ChatMessage message = new(ChatRole.Assistant, contents.ToList());
            ChatResponse response = new([message])
            {
                ModelId = "test-model",
                FinishReason = ChatFinishReason.Stop,
                Usage = new UsageDetails
                {
                    InputTokenCount = 10,
                    OutputTokenCount = 5,
                    TotalTokenCount = 15
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

            ChatMessage lastMessage = messages.Last();
            IEnumerable<AIContent> contents = this._contentProvider(lastMessage);
            List<AIContent> contentList = contents.ToList();

            // Stream each content item separately
            for (int i = 0; i < contentList.Count; i++)
            {
                List<AIContent> updateContents = [contentList[i]];

                // Add usage to the last update
                if (i == contentList.Count - 1)
                {
                    updateContents.Add(new UsageContent(new UsageDetails
                    {
                        InputTokenCount = 10,
                        OutputTokenCount = 5,
                        TotalTokenCount = 15
                    }));
                }

                yield return new ChatResponseUpdate
                {
                    Contents = updateContents,
                    Role = ChatRole.Assistant
                };
            }
        }

        public object? GetService(Type serviceType, object? serviceKey = null) =>
            serviceType.IsInstanceOfType(this) ? this : null;

        public void Dispose()
        {
        }
    }
}
