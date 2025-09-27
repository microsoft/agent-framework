// Licensed to the .NET Foundation under one or more agreements.
// The .NET Foundation licenses this file to you under the MIT license.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Runtime.CompilerServices;
using System.Threading;
using System.Threading.Tasks;
using Xunit;

namespace Microsoft.Extensions.AI;

public class UseDelegateChatClientTests
{
    [Fact]
    public void InvalidArgs_Throws()
    {
        using var client = new TestChatClient();
        ChatClientBuilder builder = new(client);

        Assert.Throws<ArgumentNullException>("getResponseFunc", () => builder.Use(null!, null!));
    }

    [Fact]
    public async Task Shared_ContextPropagated()
    {
        IList<ChatMessage> expectedMessages = [];
        ChatOptions expectedOptions = new();
        using CancellationTokenSource expectedCts = new();

        AsyncLocal<int> asyncLocal = new();

        using IChatClient innerClient = new TestChatClient
        {
            GetResponseAsyncCallback = (messages, options, cancellationToken) =>
            {
                Assert.Same(expectedMessages, messages);
                Assert.Same(expectedOptions, options);
                Assert.Equal(expectedCts.Token, cancellationToken);
                Assert.Equal(42, asyncLocal.Value);
                return Task.FromResult(new ChatResponse(new ChatMessage(ChatRole.Assistant, "hello")));
            },

            GetStreamingResponseAsyncCallback = (messages, options, cancellationToken) =>
            {
                Assert.Same(expectedMessages, messages);
                Assert.Same(expectedOptions, options);
                Assert.Equal(expectedCts.Token, cancellationToken);
                Assert.Equal(42, asyncLocal.Value);
                return YieldUpdates(new ChatResponseUpdate(null, "world"));
            },
        };

        using IChatClient client = new ChatClientBuilder(innerClient)
            .Use(async (messages, options, next, cancellationToken) =>
            {
                Assert.Same(expectedMessages, messages);
                Assert.Same(expectedOptions, options);
                Assert.Equal(expectedCts.Token, cancellationToken);
                asyncLocal.Value = 42;
                await next(messages, options, cancellationToken);
            })
            .Build();

        Assert.Equal(0, asyncLocal.Value);
        ChatResponse response = await client.GetResponseAsync(expectedMessages, expectedOptions, expectedCts.Token);
        Assert.Equal("hello", response.Text);

        Assert.Equal(0, asyncLocal.Value);
        response = await client.GetStreamingResponseAsync(expectedMessages, expectedOptions, expectedCts.Token).ToChatResponseAsync();
        Assert.Equal("world", response.Text);
    }

    [Fact]
    public async Task GetResponseFunc_ContextPropagated()
    {
        IList<ChatMessage> expectedMessages = [];
        ChatOptions expectedOptions = new();
        using CancellationTokenSource expectedCts = new();
        AsyncLocal<int> asyncLocal = new();

        using IChatClient innerClient = new TestChatClient
        {
            GetResponseAsyncCallback = (messages, options, cancellationToken) =>
            {
                Assert.Same(expectedMessages, messages);
                Assert.Same(expectedOptions, options);
                Assert.Equal(expectedCts.Token, cancellationToken);
                Assert.Equal(42, asyncLocal.Value);
                return Task.FromResult(new ChatResponse(new ChatMessage(ChatRole.Assistant, "hello")));
            },
        };

        using IChatClient client = new ChatClientBuilder(innerClient)
            .Use(async (messages, options, innerClient, cancellationToken) =>
            {
                Assert.Same(expectedMessages, messages);
                Assert.Same(expectedOptions, options);
                Assert.Equal(expectedCts.Token, cancellationToken);
                asyncLocal.Value = 42;
                var cc = await innerClient.GetResponseAsync(messages, options, cancellationToken);
                cc.Messages.SelectMany(c => c.Contents).OfType<TextContent>().Last().Text += " world";
                return cc;
            }, null)
            .Build();

        Assert.Equal(0, asyncLocal.Value);

        ChatResponse response = await client.GetResponseAsync(expectedMessages, expectedOptions, expectedCts.Token);
        Assert.Equal("hello world", response.Text);

        response = await client.GetStreamingResponseAsync(expectedMessages, expectedOptions, expectedCts.Token).ToChatResponseAsync();
        Assert.Equal("hello world", response.Text);
    }

    [Fact]
    public async Task GetStreamingResponseFunc_ContextPropagated()
    {
        IList<ChatMessage> expectedMessages = [];
        ChatOptions expectedOptions = new();
        using CancellationTokenSource expectedCts = new();
        AsyncLocal<int> asyncLocal = new();

        using IChatClient innerClient = new TestChatClient
        {
            GetStreamingResponseAsyncCallback = (messages, options, cancellationToken) =>
            {
                Assert.Same(expectedMessages, messages);
                Assert.Same(expectedOptions, options);
                Assert.Equal(expectedCts.Token, cancellationToken);
                Assert.Equal(42, asyncLocal.Value);
                return YieldUpdates(new ChatResponseUpdate(null, "hello"));
            },
        };

        using IChatClient client = new ChatClientBuilder(innerClient)
            .Use(null, (messages, options, innerClient, cancellationToken) =>
            {
                Assert.Same(expectedMessages, messages);
                Assert.Same(expectedOptions, options);
                Assert.Equal(expectedCts.Token, cancellationToken);
                asyncLocal.Value = 42;
                return Impl(messages, options, innerClient, cancellationToken);

                static async IAsyncEnumerable<ChatResponseUpdate> Impl(
                    IEnumerable<ChatMessage> messages, ChatOptions? options, IChatClient innerClient, [EnumeratorCancellation] CancellationToken cancellationToken)
                {
                    await foreach (var update in innerClient.GetStreamingResponseAsync(messages, options, cancellationToken))
                    {
                        yield return update;
                    }

                    yield return new(null, " world");
                }
            })
            .Build();

        Assert.Equal(0, asyncLocal.Value);

        ChatResponse response = await client.GetResponseAsync(expectedMessages, expectedOptions, expectedCts.Token);
        Assert.Equal("hello world", response.Text);

        response = await client.GetStreamingResponseAsync(expectedMessages, expectedOptions, expectedCts.Token).ToChatResponseAsync();
        Assert.Equal("hello world", response.Text);
    }

    [Fact]
    public async Task BothGetResponseAndGetStreamingResponseFuncs_ContextPropagated()
    {
        IList<ChatMessage> expectedMessages = [];
        ChatOptions expectedOptions = new();
        using CancellationTokenSource expectedCts = new();
        AsyncLocal<int> asyncLocal = new();

        using IChatClient innerClient = new TestChatClient
        {
            GetResponseAsyncCallback = (messages, options, cancellationToken) =>
            {
                Assert.Same(expectedMessages, messages);
                Assert.Same(expectedOptions, options);
                Assert.Equal(expectedCts.Token, cancellationToken);
                Assert.Equal(42, asyncLocal.Value);
                return Task.FromResult(new ChatResponse(new ChatMessage(ChatRole.Assistant, "non-streaming hello")));
            },

            GetStreamingResponseAsyncCallback = (messages, options, cancellationToken) =>
            {
                Assert.Same(expectedMessages, messages);
                Assert.Same(expectedOptions, options);
                Assert.Equal(expectedCts.Token, cancellationToken);
                Assert.Equal(42, asyncLocal.Value);
                return YieldUpdates(new ChatResponseUpdate(null, "streaming hello"));
            },
        };

        using IChatClient client = new ChatClientBuilder(innerClient)
            .Use(
                async (messages, options, innerClient, cancellationToken) =>
                {
                    Assert.Same(expectedMessages, messages);
                    Assert.Same(expectedOptions, options);
                    Assert.Equal(expectedCts.Token, cancellationToken);
                    asyncLocal.Value = 42;
                    var cc = await innerClient.GetResponseAsync(messages, options, cancellationToken);
                    cc.Messages.SelectMany(c => c.Contents).OfType<TextContent>().Last().Text += " world (non-streaming)";
                    return cc;
                },
                (messages, options, innerClient, cancellationToken) =>
                {
                    Assert.Same(expectedMessages, messages);
                    Assert.Same(expectedOptions, options);
                    Assert.Equal(expectedCts.Token, cancellationToken);
                    asyncLocal.Value = 42;
                    return Impl(messages, options, innerClient, cancellationToken);

                    static async IAsyncEnumerable<ChatResponseUpdate> Impl(
                        IEnumerable<ChatMessage> messages, ChatOptions? options, IChatClient innerClient, [EnumeratorCancellation] CancellationToken cancellationToken)
                    {
                        await foreach (var update in innerClient.GetStreamingResponseAsync(messages, options, cancellationToken))
                        {
                            yield return update;
                        }

                        yield return new(null, " world (streaming)");
                    }
                })
            .Build();

        Assert.Equal(0, asyncLocal.Value);

        ChatResponse response = await client.GetResponseAsync(expectedMessages, expectedOptions, expectedCts.Token);
        Assert.Equal("non-streaming hello world (non-streaming)", response.Text);

        response = await client.GetStreamingResponseAsync(expectedMessages, expectedOptions, expectedCts.Token).ToChatResponseAsync();
        Assert.Equal("streaming hello world (streaming)", response.Text);
    }

    private static async IAsyncEnumerable<ChatResponseUpdate> YieldUpdates(params ChatResponseUpdate[] updates)
    {
        foreach (var update in updates)
        {
            await Task.Yield();
            yield return update;
        }
    }
}
