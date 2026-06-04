// Copyright (c) Microsoft. All rights reserved.

using System;
using System.ClientModel.Primitives;
using System.Net;
using System.Net.Http;
using System.Text;
using System.Threading.Tasks;
using Azure.AI.Projects;
using OpenAI.Files;

#pragma warning disable OPENAI001, CS0618

namespace Microsoft.Agents.AI.Foundry.UnitTests;

/// <summary>
/// Unit tests for the file and vector-store forwarder extensions on <see cref="FoundryAgent"/>
/// declared in <see cref="FoundryAgentExtensions"/>. The forwarders are thin shims over the
/// inner <see cref="FoundryChatClient"/>, so coverage focuses on (a) request shape (the agent
/// path reaches the same wire as a direct chat-client call), (b) null/missing-FoundryChatClient
/// handling, and (c) returns the same payload the chat client would.
/// </summary>
public sealed class FoundryAgentExtensionsTests
{
    private static readonly Uri s_testProjectEndpoint = new("https://test.openai.azure.com/");

    [Fact]
    public async Task UploadFileAsync_Forwards_ToInnerFoundryChatClient_Async()
    {
        // Arrange — agent built via the Responses Agent (Mode 1) projectEndpoint+model+instructions
        // ctor wires a FoundryChatClient inside that the extension can resolve via GetService.
        var sawPostToFiles = false;
        using var handler = new HttpHandlerAssert(req =>
        {
            if (req.Method == HttpMethod.Post && req.RequestUri!.AbsolutePath.Contains("/files", StringComparison.Ordinal))
            {
                sawPostToFiles = true;
                return new HttpResponseMessage(HttpStatusCode.OK)
                {
                    Content = new StringContent(FakeFileJson("file_via_agent"), Encoding.UTF8, "application/json"),
                };
            }
            return new HttpResponseMessage(HttpStatusCode.OK) { Content = new StringContent("{}", Encoding.UTF8, "application/json") };
        });
#pragma warning disable CA5399
        using var httpClient = new HttpClient(handler);
#pragma warning restore CA5399

        var agent = new FoundryAgent(
            projectEndpoint: s_testProjectEndpoint,
            credential: new FakeAuthenticationTokenProvider(),
            model: "gpt-4o-mini",
            instructions: "Be helpful.",
            clientOptions: new AIProjectClientOptions { Transport = new HttpClientPipelineTransport(httpClient) });

        var path = System.IO.Path.Combine(System.IO.Path.GetTempPath(), $"fae-{Guid.NewGuid():N}.txt");
        System.IO.File.WriteAllText(path, "hello");

        try
        {
            // Act — call the forwarder on the agent.
            var result = await agent.UploadFileAsync(path, FileUploadPurpose.Assistants);

            // Assert
            Assert.True(sawPostToFiles, "POST to /files must reach the wire through the agent forwarder.");
            Assert.Equal("file_via_agent", result.Id);
        }
        finally
        {
            System.IO.File.Delete(path);
        }
    }

    [Fact]
    public async Task DeleteFileAsync_Forwards_ToInnerFoundryChatClient_Async()
    {
        var sawDelete = false;
        using var handler = new HttpHandlerAssert(req =>
        {
            if (req.Method == HttpMethod.Delete && req.RequestUri!.AbsolutePath.Contains("/files/", StringComparison.Ordinal))
            {
                sawDelete = true;
                return new HttpResponseMessage(HttpStatusCode.OK)
                {
                    Content = new StringContent("{\"id\":\"file_abc\",\"object\":\"file\",\"deleted\":true}", Encoding.UTF8, "application/json"),
                };
            }
            return new HttpResponseMessage(HttpStatusCode.OK) { Content = new StringContent("{}", Encoding.UTF8, "application/json") };
        });
#pragma warning disable CA5399
        using var httpClient = new HttpClient(handler);
#pragma warning restore CA5399

        var agent = new FoundryAgent(
            projectEndpoint: s_testProjectEndpoint,
            credential: new FakeAuthenticationTokenProvider(),
            model: "gpt-4o-mini",
            instructions: "Be helpful.",
            clientOptions: new AIProjectClientOptions { Transport = new HttpClientPipelineTransport(httpClient) });

        var result = await agent.DeleteFileAsync("file_abc");

        Assert.True(sawDelete);
        Assert.NotNull(result);
    }

    [Fact]
    public async Task CreateVectorStoreAsync_Forwards_ToInnerFoundryChatClient_Async()
    {
        var sawVectorStorePost = false;
        using var handler = new HttpHandlerAssert(req =>
        {
            if (req.Method == HttpMethod.Post && req.RequestUri!.AbsolutePath.Contains("/vector_stores", StringComparison.Ordinal))
            {
                sawVectorStorePost = true;
                return new HttpResponseMessage(HttpStatusCode.OK)
                {
                    Content = new StringContent(FakeVectorStoreJson("vs_via_agent", "kb"), Encoding.UTF8, "application/json"),
                };
            }
            return new HttpResponseMessage(HttpStatusCode.OK) { Content = new StringContent("{}", Encoding.UTF8, "application/json") };
        });
#pragma warning disable CA5399
        using var httpClient = new HttpClient(handler);
#pragma warning restore CA5399

        var agent = new FoundryAgent(
            projectEndpoint: s_testProjectEndpoint,
            credential: new FakeAuthenticationTokenProvider(),
            model: "gpt-4o-mini",
            instructions: "Be helpful.",
            clientOptions: new AIProjectClientOptions { Transport = new HttpClientPipelineTransport(httpClient) });

        var store = await agent.CreateVectorStoreAsync("kb", Array.Empty<string>());

        Assert.True(sawVectorStorePost);
        Assert.Equal("vs_via_agent", store.Id);
    }

    [Fact]
    public async Task DeleteVectorStoreAsync_Forwards_ToInnerFoundryChatClient_Async()
    {
        var sawDelete = false;
        using var handler = new HttpHandlerAssert(req =>
        {
            if (req.Method == HttpMethod.Delete && req.RequestUri!.AbsolutePath.Contains("/vector_stores/", StringComparison.Ordinal))
            {
                sawDelete = true;
                return new HttpResponseMessage(HttpStatusCode.OK)
                {
                    Content = new StringContent("{\"id\":\"vs_abc\",\"object\":\"vector_store.deleted\",\"deleted\":true}", Encoding.UTF8, "application/json"),
                };
            }
            return new HttpResponseMessage(HttpStatusCode.OK) { Content = new StringContent("{}", Encoding.UTF8, "application/json") };
        });
#pragma warning disable CA5399
        using var httpClient = new HttpClient(handler);
#pragma warning restore CA5399

        var agent = new FoundryAgent(
            projectEndpoint: s_testProjectEndpoint,
            credential: new FakeAuthenticationTokenProvider(),
            model: "gpt-4o-mini",
            instructions: "Be helpful.",
            clientOptions: new AIProjectClientOptions { Transport = new HttpClientPipelineTransport(httpClient) });

        await agent.DeleteVectorStoreAsync("vs_abc");

        Assert.True(sawDelete);
    }

    [Fact]
    public async Task UploadFileAsync_NullAgent_ThrowsArgumentNullExceptionAsync()
        => await Assert.ThrowsAsync<ArgumentNullException>(() =>
            FoundryAgentExtensions.UploadFileAsync(null!, "x", FileUploadPurpose.Assistants));

    [Fact]
    public async Task DeleteFileAsync_NullAgent_ThrowsArgumentNullExceptionAsync()
        => await Assert.ThrowsAsync<ArgumentNullException>(() =>
            FoundryAgentExtensions.DeleteFileAsync(null!, "file_abc"));

    [Fact]
    public async Task CreateVectorStoreAsync_NullAgent_ThrowsArgumentNullExceptionAsync()
        => await Assert.ThrowsAsync<ArgumentNullException>(() =>
            FoundryAgentExtensions.CreateVectorStoreAsync(null!, "kb", Array.Empty<string>()));

    [Fact]
    public async Task DeleteVectorStoreAsync_NullAgent_ThrowsArgumentNullExceptionAsync()
        => await Assert.ThrowsAsync<ArgumentNullException>(() =>
            FoundryAgentExtensions.DeleteVectorStoreAsync(null!, "vs_abc"));

    // ----- Helpers -----

    private static string FakeFileJson(string id)
        => $"{{\"id\":\"{id}\",\"object\":\"file\",\"bytes\":11,\"created_at\":1700000000,\"filename\":\"x.txt\",\"purpose\":\"assistants\",\"status\":\"processed\"}}";

    private static string FakeVectorStoreJson(string id, string name)
        => $"{{\"id\":\"{id}\",\"object\":\"vector_store\",\"created_at\":1700000000,\"name\":\"{name}\",\"usage_bytes\":0,\"file_counts\":{{\"in_progress\":0,\"completed\":0,\"failed\":0,\"cancelled\":0,\"total\":0}},\"status\":\"completed\",\"last_active_at\":1700000000}}";
}
#pragma warning restore CS0618
