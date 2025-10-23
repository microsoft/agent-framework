// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.IO;
using System.Net.Http;
using System.Text;
using System.Text.Json;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Hosting.OpenAI.UnitTests;
using Microsoft.AspNetCore.Builder;
using Microsoft.AspNetCore.Hosting.Server;
using Microsoft.AspNetCore.TestHost;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Hosting;

namespace Microsoft.Agents.AI.Hosting.OpenAI.Tests;

/// <summary>
/// Base class for conformance tests that load request/response traces from disk.
/// </summary>
public abstract class ConformanceTestBase : IAsyncDisposable
{
    protected const string TracesBasePath = "ConformanceTraces/Responses";
    private WebApplication? _app;
    private HttpClient? _httpClient;

    /// <summary>
    /// Loads a JSON file from the conformance traces directory.
    /// </summary>
    protected static string LoadTraceFile(string relativePath)
    {
        var fullPath = Path.Combine(TracesBasePath, relativePath);

        if (!File.Exists(fullPath))
        {
            throw new FileNotFoundException($"Conformance trace file not found: {fullPath}");
        }

        return File.ReadAllText(fullPath);
    }

    /// <summary>
    /// Loads a JSON document from the conformance traces directory.
    /// </summary>
    protected static JsonDocument LoadTraceDocument(string relativePath)
    {
        var json = LoadTraceFile(relativePath);
        return JsonDocument.Parse(json);
    }

    /// <summary>
    /// Asserts that a JSON element exists (property is present, value can be null).
    /// </summary>
    protected static void AssertJsonPropertyExists(JsonElement element, string propertyName)
    {
        if (!element.TryGetProperty(propertyName, out _))
        {
            throw new Xunit.Sdk.XunitException($"Expected property '{propertyName}' not found in JSON");
        }
    }

    /// <summary>
    /// Asserts that a JSON element has a specific string value.
    /// </summary>
    protected static void AssertJsonPropertyEquals(JsonElement element, string propertyName, string expectedValue)
    {
        AssertJsonPropertyExists(element, propertyName);
        var actualValue = element.GetProperty(propertyName).GetString();

        if (actualValue != expectedValue)
        {
            throw new Xunit.Sdk.XunitException($"Property '{propertyName}': expected '{expectedValue}', got '{actualValue}'");
        }
    }

    /// <summary>
    /// Asserts that a JSON element has a specific integer value.
    /// </summary>
    protected static void AssertJsonPropertyEquals(JsonElement element, string propertyName, int expectedValue)
    {
        AssertJsonPropertyExists(element, propertyName);
        var actualValue = element.GetProperty(propertyName).GetInt32();

        if (actualValue != expectedValue)
        {
            throw new Xunit.Sdk.XunitException($"Property '{propertyName}': expected {expectedValue}, got {actualValue}");
        }
    }

    /// <summary>
    /// Asserts that a JSON element has a specific boolean value.
    /// </summary>
    protected static void AssertJsonPropertyEquals(JsonElement element, string propertyName, bool expectedValue)
    {
        AssertJsonPropertyExists(element, propertyName);
        var actualValue = element.GetProperty(propertyName).GetBoolean();

        if (actualValue != expectedValue)
        {
            throw new Xunit.Sdk.XunitException($"Property '{propertyName}': expected {expectedValue}, got {actualValue}");
        }
    }

    /// <summary>
    /// Gets a property value or returns a default if the property doesn't exist.
    /// </summary>
    protected static T GetPropertyOrDefault<T>(JsonElement element, string propertyName, T defaultValue = default!)
    {
        if (!element.TryGetProperty(propertyName, out var property))
        {
            return defaultValue;
        }

        if (property.ValueKind == JsonValueKind.Null)
        {
            return defaultValue;
        }

        return typeof(T) switch
        {
            Type t when t == typeof(string) => (T)(object)property.GetString()!,
            Type t when t == typeof(int) => (T)(object)property.GetInt32(),
            Type t when t == typeof(long) => (T)(object)property.GetInt64(),
            Type t when t == typeof(bool) => (T)(object)property.GetBoolean(),
            Type t when t == typeof(double) => (T)(object)property.GetDouble(),
            _ => throw new NotSupportedException($"Type {typeof(T)} not supported")
        };
    }

    /// <summary>
    /// Creates a test server with a mock chat client that returns the expected response text.
    /// </summary>
    protected async Task<HttpClient> CreateTestServerAsync(string agentName, string instructions, string responseText)
    {
        WebApplicationBuilder builder = WebApplication.CreateBuilder();
        builder.WebHost.UseTestServer();

        IChatClient mockChatClient = new TestHelpers.SimpleMockChatClient(responseText);
        builder.Services.AddKeyedSingleton("chat-client", mockChatClient);
        builder.AddAIAgent(agentName, instructions, chatClientServiceKey: "chat-client");
        builder.AddOpenAIResponses();

        this._app = builder.Build();
        AIAgent agent = this._app.Services.GetRequiredKeyedService<AIAgent>(agentName);
        this._app.MapOpenAIResponses(agent);

        await this._app.StartAsync();

        TestServer testServer = this._app.Services.GetRequiredService<IServer>() as TestServer
            ?? throw new InvalidOperationException("TestServer not found");

        this._httpClient = testServer.CreateClient();
        return this._httpClient;
    }

    /// <summary>
    /// Creates a test server with a mock chat client that returns custom content.
    /// </summary>
    protected async Task<HttpClient> CreateTestServerAsync(
        string agentName,
        string instructions,
        string responseText,
        Func<ChatMessage, IEnumerable<AIContent>> contentProvider)
    {
        WebApplicationBuilder builder = WebApplication.CreateBuilder();
        builder.WebHost.UseTestServer();

        IChatClient mockChatClient = new TestHelpers.CustomContentMockChatClient(contentProvider);
        builder.Services.AddKeyedSingleton("chat-client", mockChatClient);
        builder.AddAIAgent(agentName, instructions, chatClientServiceKey: "chat-client");
        builder.AddOpenAIResponses();

        this._app = builder.Build();
        AIAgent agent = this._app.Services.GetRequiredKeyedService<AIAgent>(agentName);
        this._app.MapOpenAIResponses(agent);

        await this._app.StartAsync();

        TestServer testServer = this._app.Services.GetRequiredService<IServer>() as TestServer
            ?? throw new InvalidOperationException("TestServer not found");

        this._httpClient = testServer.CreateClient();
        return this._httpClient;
    }

    /// <summary>
    /// Sends a POST request with JSON content to the test server.
    /// </summary>
    protected async Task<HttpResponseMessage> SendRequestAsync(HttpClient client, string agentName, string requestJson)
    {
        StringContent content = new(requestJson, Encoding.UTF8, "application/json");
        return await client.PostAsync(new Uri($"/{agentName}/v1/responses", UriKind.Relative), content);
    }

    /// <summary>
    /// Parses the response JSON and returns a JsonDocument.
    /// </summary>
    protected static async Task<JsonDocument> ParseResponseAsync(HttpResponseMessage response)
    {
        string responseJson = await response.Content.ReadAsStringAsync();
        return JsonDocument.Parse(responseJson);
    }

    public async ValueTask DisposeAsync()
    {
        this._httpClient?.Dispose();
        if (this._app != null)
        {
            await this._app.DisposeAsync();
        }

        GC.SuppressFinalize(this);
    }
}
