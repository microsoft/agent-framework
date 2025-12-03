// Copyright (c) Microsoft. All rights reserved.

using System;
using System.ClientModel.Primitives;
using System.Net;
using System.Net.Http;
using System.Text;
using System.Threading.Tasks;
using Azure.AI.Projects;

namespace Microsoft.Agents.AI.AzureAI.UnitTests;

public class AzureAIProjectChatClientTests
{
    /// <summary>
    /// Verify that when the ChatOptions has a "conv_" prefixed conversation ID, the chat client uses conversation in the http requests via the chat client
    /// </summary>
    [Fact]
    public async Task ChatClient_UsesDefaultConversationIdAsync()
    {
        // Arrange
        var requestTriggered = false;
        using var httpHandler = new HttpHandlerAssert(async (request) =>
        {
            if (request.RequestUri!.PathAndQuery.Contains("openai/responses"))
            {
                requestTriggered = true;

                // Assert
                if (request.Content is not null)
                {
                    var requestBody = await request.Content.ReadAsStringAsync().ConfigureAwait(false);
                    Assert.Contains("conv_12345", requestBody);
                }

                return new HttpResponseMessage(HttpStatusCode.OK) { Content = new StringContent(TestDataUtil.GetOpenAIDefaultResponseJson(), Encoding.UTF8, "application/json") };
            }

            return new HttpResponseMessage(HttpStatusCode.OK) { Content = new StringContent(TestDataUtil.GetAgentResponseJson(), Encoding.UTF8, "application/json") };
        });

#pragma warning disable CA5399
        using var httpClient = new HttpClient(httpHandler);
#pragma warning restore CA5399

        var client = new AIProjectClient(new Uri("https://test.openai.azure.com/"), new FakeAuthenticationTokenProvider(), new() { Transport = new HttpClientPipelineTransport(httpClient) });

        var agent = await client.GetAIAgentAsync(
            new ChatClientAgentOptions
            {
                Name = "test-agent",
                ChatOptions = new() { Instructions = "Test instructions", ConversationId = "conv_12345" }
            });

        // Act
        var thread = agent.GetNewThread();
        await agent.RunAsync("Hello", thread);

        Assert.True(requestTriggered);
        var chatClientThread = Assert.IsType<ChatClientAgentThread>(thread);
        Assert.Equal("conv_12345", chatClientThread.ConversationId);
    }

    /// <summary>
    /// Verify that when the chat client doesn't have a default "conv_" conversation id, the chat client still uses the conversation ID in HTTP requests.
    /// </summary>
    [Fact]
    public async Task ChatClient_UsesPerRequestConversationId_WhenNoDefaultConversationIdIsProvidedAsync()
    {
        // Arrange
        var requestTriggered = false;
        using var httpHandler = new HttpHandlerAssert(async (request) =>
        {
            if (request.RequestUri!.PathAndQuery.Contains("openai/responses"))
            {
                requestTriggered = true;

                // Assert
                if (request.Content is not null)
                {
                    var requestBody = await request.Content.ReadAsStringAsync().ConfigureAwait(false);
                    Assert.Contains("conv_12345", requestBody);
                }

                return new HttpResponseMessage(HttpStatusCode.OK) { Content = new StringContent(TestDataUtil.GetOpenAIDefaultResponseJson(), Encoding.UTF8, "application/json") };
            }

            return new HttpResponseMessage(HttpStatusCode.OK) { Content = new StringContent(TestDataUtil.GetAgentResponseJson(), Encoding.UTF8, "application/json") };
        });

#pragma warning disable CA5399
        using var httpClient = new HttpClient(httpHandler);
#pragma warning restore CA5399

        var client = new AIProjectClient(new Uri("https://test.openai.azure.com/"), new FakeAuthenticationTokenProvider(), new() { Transport = new HttpClientPipelineTransport(httpClient) });

        var agent = await client.GetAIAgentAsync(
            new ChatClientAgentOptions
            {
                Name = "test-agent",
                ChatOptions = new() { Instructions = "Test instructions" },
            });

        // Act
        var thread = agent.GetNewThread();
        await agent.RunAsync("Hello", thread, options: new ChatClientAgentRunOptions() { ChatOptions = new() { ConversationId = "conv_12345" } });

        Assert.True(requestTriggered);
        var chatClientThread = Assert.IsType<ChatClientAgentThread>(thread);
        Assert.Equal("conv_12345", chatClientThread.ConversationId);
    }

    /// <summary>
    /// Verify that even when the chat client has a default conversation id, the chat client will prioritize the per-request conversation id provided in HTTP requests.
    /// </summary>
    [Fact]
    public async Task ChatClient_UsesPerRequestConversationId_EvenWhenDefaultConversationIdIsProvidedAsync()
    {
        // Arrange
        var requestTriggered = false;
        using var httpHandler = new HttpHandlerAssert(async (request) =>
        {
            if (request.RequestUri!.PathAndQuery.Contains("openai/responses"))
            {
                requestTriggered = true;

                // Assert
                if (request.Content is not null)
                {
                    var requestBody = await request.Content.ReadAsStringAsync().ConfigureAwait(false);
                    Assert.Contains("conv_12345", requestBody);
                }

                return new HttpResponseMessage(HttpStatusCode.OK) { Content = new StringContent(TestDataUtil.GetOpenAIDefaultResponseJson(), Encoding.UTF8, "application/json") };
            }

            return new HttpResponseMessage(HttpStatusCode.OK) { Content = new StringContent(TestDataUtil.GetAgentResponseJson(), Encoding.UTF8, "application/json") };
        });

#pragma warning disable CA5399
        using var httpClient = new HttpClient(httpHandler);
#pragma warning restore CA5399

        var client = new AIProjectClient(new Uri("https://test.openai.azure.com/"), new FakeAuthenticationTokenProvider(), new() { Transport = new HttpClientPipelineTransport(httpClient) });

        var agent = await client.GetAIAgentAsync(
            new ChatClientAgentOptions
            {
                Name = "test-agent",
                ChatOptions = new() { Instructions = "Test instructions", ConversationId = "conv_should_not_use_default" }
            });

        // Act
        var thread = agent.GetNewThread();
        await agent.RunAsync("Hello", thread, options: new ChatClientAgentRunOptions() { ChatOptions = new() { ConversationId = "conv_12345" } });

        Assert.True(requestTriggered);
        var chatClientThread = Assert.IsType<ChatClientAgentThread>(thread);
        Assert.Equal("conv_12345", chatClientThread.ConversationId);
    }

    /// <summary>
    /// Verify that when the chat client is provided without a "conv_" prefixed conversation ID, the chat client uses the previous conversation ID in HTTP requests.
    /// </summary>
    [Fact]
    public async Task ChatClient_UsesPreviousResponseId_WhenConversationIsNotPrefixedAsConvAsync()
    {
        // Arrange
        var requestTriggered = false;
        using var httpHandler = new HttpHandlerAssert(async (request) =>
        {
            if (request.RequestUri!.PathAndQuery.Contains("openai/responses"))
            {
                requestTriggered = true;

                // Assert
                if (request.Content is not null)
                {
                    var requestBody = await request.Content.ReadAsStringAsync().ConfigureAwait(false);
                    Assert.Contains("resp_0888a", requestBody);
                }

                return new HttpResponseMessage(HttpStatusCode.OK) { Content = new StringContent(TestDataUtil.GetOpenAIDefaultResponseJson(), Encoding.UTF8, "application/json") };
            }

            return new HttpResponseMessage(HttpStatusCode.OK) { Content = new StringContent(TestDataUtil.GetAgentResponseJson(), Encoding.UTF8, "application/json") };
        });

#pragma warning disable CA5399
        using var httpClient = new HttpClient(httpHandler);
#pragma warning restore CA5399

        var client = new AIProjectClient(new Uri("https://test.openai.azure.com/"), new FakeAuthenticationTokenProvider(), new() { Transport = new HttpClientPipelineTransport(httpClient) });

        var agent = await client.GetAIAgentAsync(
            new ChatClientAgentOptions
            {
                Name = "test-agent",
                ChatOptions = new() { Instructions = "Test instructions" },
            });

        // Act
        var thread = agent.GetNewThread();
        await agent.RunAsync("Hello", thread, options: new ChatClientAgentRunOptions() { ChatOptions = new() { ConversationId = "resp_0888a" } });

        Assert.True(requestTriggered);
        var chatClientThread = Assert.IsType<ChatClientAgentThread>(thread);
        Assert.Equal("resp_0888a46cbf2b1ff3006914596e05d08195a77c3f5187b769a7", chatClientThread.ConversationId);
    }
}
