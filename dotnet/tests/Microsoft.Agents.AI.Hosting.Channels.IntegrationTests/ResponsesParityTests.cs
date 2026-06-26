// Copyright (c) Microsoft. All rights reserved.

using System.Net;
using System.Net.Http;
using System.Text;
using System.Text.Json;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Hosting.Channels.IntegrationTests.Support;
using Microsoft.Agents.AI.Hosting.Channels.Responses;
using Microsoft.Extensions.Hosting;

namespace Microsoft.Agents.AI.Hosting.Channels.IntegrationTests;

/// <summary>
/// Python-parity coverage for the Responses channel: session anchoring via <c>previous_response_id</c>,
/// generation-option forwarding (stripped by default, kept by a custom run hook), caller identity, and the
/// richer input-parsing surface (content parts, image/file inputs, 422 on malformed shapes).
/// </summary>
public class ResponsesParityTests
{
    [Fact]
    public async Task PreviousResponseId_ResumesSessionAsync()
    {
        // Arrange - default channel, session-counting agent
        await using var app = await TestHostApp.StartAsync(b => b.AddAgentFrameworkHost(new CountingAgent()).AddResponsesChannel());

        // Act - first turn mints a response id that anchors the session
        var (firstText, responseId) = await PostAndReadAsync(app, "{ \"input\": \"hi\" }");

        // Second turn replays that id as previous_response_id -> same isolation key -> same session
        var (secondText, _) = await PostAndReadAsync(app, $"{{ \"input\": \"hi\", \"previous_response_id\": \"{responseId}\" }}");

        // Assert - the count increments, proving the session resumed
        Assert.Equal("1", firstText);
        Assert.Equal("2", secondText);
    }

    [Fact]
    public async Task NewRequests_WithoutPreviousId_PartitionAsync()
    {
        // Arrange
        await using var app = await TestHostApp.StartAsync(b => b.AddAgentFrameworkHost(new CountingAgent()).AddResponsesChannel());

        // Act - two unrelated first turns each mint their own anchor
        var (first, _) = await PostAndReadAsync(app, "{ \"input\": \"hi\" }");
        var (second, _) = await PostAndReadAsync(app, "{ \"input\": \"hi\" }");

        // Assert - distinct response ids partition into fresh sessions
        Assert.Equal("1", first);
        Assert.Equal("1", second);
    }

    [Fact]
    public async Task DefaultChannel_StripsGenerationOptionsAsync()
    {
        // Arrange - no run hook => default strip
        var agent = new RecordingAgent();
        await using var app = await TestHostApp.StartAsync(b => b.AddAgentFrameworkHost(agent).AddResponsesChannel());

        // Act
        await PostAsync(app, "{ \"input\": \"hi\", \"max_output_tokens\": 7, \"temperature\": 0.5 }");

        // Assert - parsed options were stripped before reaching the agent
        Assert.True(agent.RunCalled);
        Assert.Null(agent.LastChatOptions);
    }

    [Fact]
    public async Task CustomRunHook_ForwardsGenerationOptionsAsync()
    {
        // Arrange - a run hook replaces the default strip and keeps options
        var agent = new RecordingAgent();
        await using var app = await TestHostApp.StartAsync(b => b.AddAgentFrameworkHost(agent).AddResponsesChannel(o => o.RunHook = new CapturingRunHook()));

        // Act
        await PostAsync(app, "{ \"input\": \"hi\", \"max_output_tokens\": 7, \"parallel_tool_calls\": true }");

        // Assert - remapped generation options reached the agent
        Assert.NotNull(agent.LastChatOptions);
        Assert.Equal(7, agent.LastChatOptions!.MaxOutputTokens);
        Assert.True(agent.LastChatOptions.AllowMultipleToolCalls);
    }

    [Fact]
    public async Task SafetyIdentifier_SurfacedAsIdentityAsync()
    {
        // Arrange
        var hook = new CapturingRunHook();
        await using var app = await TestHostApp.StartAsync(b => b.AddAgentFrameworkHost(new EchoAgent()).AddResponsesChannel(o => o.RunHook = hook));

        // Act
        await PostAsync(app, "{ \"input\": \"hi\", \"safety_identifier\": \"u-123\" }");

        // Assert
        Assert.NotNull(hook.Last);
        Assert.NotNull(hook.Last!.Identity);
        Assert.Equal("responses", hook.Last.Identity!.Channel);
        Assert.Equal("u-123", hook.Last.Identity.NativeId);
    }

    [Fact]
    public async Task User_FallbackSurfacedAsIdentityAsync()
    {
        // Arrange
        var hook = new CapturingRunHook();
        await using var app = await TestHostApp.StartAsync(b => b.AddAgentFrameworkHost(new EchoAgent()).AddResponsesChannel(o => o.RunHook = hook));

        // Act - legacy `user` field falls back when safety_identifier is absent
        await PostAsync(app, "{ \"input\": \"hi\", \"user\": \"legacy-uid\" }");

        // Assert
        Assert.Equal("legacy-uid", hook.Last!.Identity!.NativeId);
    }

    [Fact]
    public async Task MessageEnvelope_WithInputTextContent_IsParsedAsync()
    {
        // Arrange
        await using var app = await TestHostApp.StartAsync(b => b.AddAgentFrameworkHost(new EchoAgent()).AddResponsesChannel());

        // Act - message envelope carrying an input_text content part
        var body = await PostReadBodyAsync(app, "{ \"input\": [ { \"type\": \"message\", \"role\": \"user\", \"content\": [ { \"type\": \"input_text\", \"text\": \"hello\" } ] } ] }");

        // Assert
        Assert.Contains("hello", body);
    }

    [Fact]
    public async Task LooseContentPart_IsParsedAsync()
    {
        // Arrange
        await using var app = await TestHostApp.StartAsync(b => b.AddAgentFrameworkHost(new EchoAgent()).AddResponsesChannel());

        // Act - a bare content part (no message envelope) buffers into a user message
        var body = await PostReadBodyAsync(app, "{ \"input\": [ { \"type\": \"input_text\", \"text\": \"loose\" } ] }");

        // Assert
        Assert.Contains("loose", body);
    }

    [Fact]
    public async Task InputImage_IsAcceptedAsync()
    {
        // Arrange
        await using var app = await TestHostApp.StartAsync(b => b.AddAgentFrameworkHost(new EchoAgent()).AddResponsesChannel());

        // Act
        var response = await PostAsync(app, "{ \"input\": [ { \"type\": \"input_image\", \"image_url\": \"https://example.com/a.png\" } ] }");

        // Assert - image input parses (not a 422)
        Assert.Equal(HttpStatusCode.OK, response.StatusCode);
    }

    [Fact]
    public async Task UnsupportedContentType_Returns422Async()
    {
        // Arrange
        await using var app = await TestHostApp.StartAsync(b => b.AddAgentFrameworkHost(new EchoAgent()).AddResponsesChannel());

        // Act
        var response = await PostAsync(app, "{ \"input\": [ { \"type\": \"input_audio\", \"audio\": \"x\" } ] }");

        // Assert
        Assert.Equal(HttpStatusCode.UnprocessableEntity, response.StatusCode);
    }

    [Fact]
    public async Task NonObjectArrayItem_Returns422Async()
    {
        // Arrange
        await using var app = await TestHostApp.StartAsync(b => b.AddAgentFrameworkHost(new EchoAgent()).AddResponsesChannel());

        // Act - a bare string array item is not a valid input object
        var response = await PostAsync(app, "{ \"input\": [ \"bare\" ] }");

        // Assert
        Assert.Equal(HttpStatusCode.UnprocessableEntity, response.StatusCode);
    }

    [Fact]
    public async Task InputFile_WithoutUrlOrId_Returns422Async()
    {
        // Arrange
        await using var app = await TestHostApp.StartAsync(b => b.AddAgentFrameworkHost(new EchoAgent()).AddResponsesChannel());

        // Act
        var response = await PostAsync(app, "{ \"input\": [ { \"type\": \"input_file\" } ] }");

        // Assert
        Assert.Equal(HttpStatusCode.UnprocessableEntity, response.StatusCode);
    }

    private static StringContent Json(string body) => new(body, Encoding.UTF8, "application/json");

    private static Task<HttpResponseMessage> PostAsync(TestHostApp app, string body) =>
        app.Client.PostAsync(new System.Uri("http://localhost/responses"), Json(body));

    private static async Task<string> PostReadBodyAsync(TestHostApp app, string body)
    {
        var response = await PostAsync(app, body);
        return await response.Content.ReadAsStringAsync();
    }

    private static async Task<(string Text, string ResponseId)> PostAndReadAsync(TestHostApp app, string body)
    {
        var raw = await PostReadBodyAsync(app, body);
        using var doc = JsonDocument.Parse(raw);
        var text = doc.RootElement.GetProperty("output")[0].GetProperty("content")[0].GetProperty("text").GetString()!;
        var id = doc.RootElement.GetProperty("id").GetString()!;
        return (text, id);
    }
}
