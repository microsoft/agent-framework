// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Net;
using System.Net.Http;
using System.Text;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Hosting.Channels.IntegrationTests.Support;
using Microsoft.Agents.AI.Hosting.Channels.Responses;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.Hosting;

namespace Microsoft.Agents.AI.Hosting.Channels.IntegrationTests;

/// <summary>
/// Parser-parity coverage: asserts the parsed <see cref="ChatMessage"/> content (not just HTTP status) by
/// capturing the <see cref="ChannelRequest"/> the channel built, mirroring Python's <c>test_parsing.py</c>.
/// </summary>
public class ResponsesParsingParityTests
{
    private static async Task<ChannelRequest> CaptureAsync(string body)
    {
        var hook = new CapturingRunHook();
        await using var app = await TestHostApp.StartAsync(b => b.AddAgentFrameworkHost(new EchoAgent()).AddResponsesChannel(o => o.RunHook = hook));
        var response = await app.Client.PostAsync(new Uri("http://localhost/responses"), Json(body));
        Assert.Equal(HttpStatusCode.OK, response.StatusCode);
        Assert.NotNull(hook.Last);
        return hook.Last!;
    }

    private static IReadOnlyList<ChatMessage> Messages(ChannelRequest request) => Assert.IsAssignableFrom<IReadOnlyList<ChatMessage>>(request.Input);

    [Fact]
    public async Task StringInput_BecomesSingleUserTextMessageAsync()
    {
        var request = await CaptureAsync("{ \"input\": \"hi\" }");
        var messages = Messages(request);
        Assert.Single(messages);
        Assert.Equal(ChatRole.User, messages[0].Role);
        Assert.Equal("hi", Assert.IsType<TextContent>(Assert.Single(messages[0].Contents)).Text);
    }

    [Fact]
    public async Task MessageEnvelope_MapsRoleAndTextAsync()
    {
        var request = await CaptureAsync("{ \"input\": [ { \"type\": \"message\", \"role\": \"assistant\", \"content\": \"prior\" } ] }");
        var messages = Messages(request);
        Assert.Single(messages);
        Assert.Equal(ChatRole.Assistant, messages[0].Role);
        Assert.Equal("prior", Assert.IsType<TextContent>(Assert.Single(messages[0].Contents)).Text);
    }

    [Fact]
    public async Task LooseText_FlushesAsUserMessageBeforeEnvelopeAsync()
    {
        var request = await CaptureAsync("{ \"input\": [ { \"type\": \"input_text\", \"text\": \"loose\" }, { \"type\": \"message\", \"role\": \"assistant\", \"content\": \"prior\" } ] }");
        var messages = Messages(request);
        Assert.Equal(2, messages.Count);
        Assert.Equal(ChatRole.User, messages[0].Role);
        Assert.Equal("loose", Assert.IsType<TextContent>(Assert.Single(messages[0].Contents)).Text);
        Assert.Equal(ChatRole.Assistant, messages[1].Role);
    }

    [Fact]
    public async Task InputImage_StringUrl_BecomesUriContentAsync()
    {
        var request = await CaptureAsync("{ \"input\": [ { \"type\": \"input_image\", \"image_url\": \"https://example.com/a.png\" } ] }");
        var content = Assert.Single(Messages(request)[0].Contents);
        Assert.Equal("https://example.com/a.png", Assert.IsType<UriContent>(content).Uri.ToString());
    }

    [Fact]
    public async Task InputImage_ObjectUrl_BecomesUriContentAsync()
    {
        var request = await CaptureAsync("{ \"input\": [ { \"type\": \"input_image\", \"image_url\": { \"url\": \"https://example.com/b.png\" } } ] }");
        var content = Assert.Single(Messages(request)[0].Contents);
        Assert.Equal("https://example.com/b.png", Assert.IsType<UriContent>(content).Uri.ToString());
    }

    [Fact]
    public async Task InputFile_Url_BecomesUriContentAsync()
    {
        var request = await CaptureAsync("{ \"input\": [ { \"type\": \"input_file\", \"file_url\": \"https://example.com/d.pdf\", \"mime_type\": \"application/pdf\" } ] }");
        var content = Assert.Single(Messages(request)[0].Contents);
        var uri = Assert.IsType<UriContent>(content);
        Assert.Equal("https://example.com/d.pdf", uri.Uri.ToString());
        Assert.Equal("application/pdf", uri.MediaType);
    }

    [Fact]
    public async Task InputFile_FileId_BecomesHostedFileContentAsync()
    {
        var request = await CaptureAsync("{ \"input\": [ { \"type\": \"input_file\", \"file_id\": \"file-123\" } ] }");
        var content = Assert.Single(Messages(request)[0].Contents);
        Assert.Equal("file-123", Assert.IsType<HostedFileContent>(content).FileId);
    }

    [Fact]
    public async Task Identity_AbsentWhenNoIdentifierAsync()
    {
        var request = await CaptureAsync("{ \"input\": \"hi\" }");
        Assert.Null(request.Identity);
    }

    [Fact]
    public async Task Identity_SafetyIdentifierPreferredOverUserAsync()
    {
        var request = await CaptureAsync("{ \"input\": \"hi\", \"safety_identifier\": \"abc\", \"user\": \"legacy\" }");
        Assert.NotNull(request.Identity);
        Assert.Equal("abc", request.Identity!.NativeId);
    }

    [Fact]
    public async Task Identity_NonStringSafetyIdentifierIsIgnoredAsync()
    {
        // Python parse_responses_identity returns None for a non-string identifier rather than rejecting the
        // request; the channel must tolerate it and surface no identity (HTTP 200, not 400).
        var request = await CaptureAsync("{ \"input\": \"hi\", \"safety_identifier\": 42 }");
        Assert.Null(request.Identity);
    }

    [Theory]
    [InlineData("{ \"input\": 123 }")]
    [InlineData("{ \"input\": [] }")]
    [InlineData("{ \"input\": [ { \"type\": \"message\", \"role\": \"user\", \"content\": 123 } ] }")]
    [InlineData("{ \"input\": [ { \"type\": \"message\", \"role\": \"user\", \"content\": [ 123 ] } ] }")]
    [InlineData("{ \"input\": [ { \"type\": \"input_image\" } ] }")]
    public async Task MalformedInput_Returns422Async(string body)
    {
        await using var app = await TestHostApp.StartAsync(b => b.AddAgentFrameworkHost(new EchoAgent()).AddResponsesChannel());
        var response = await app.Client.PostAsync(new Uri("http://localhost/responses"), Json(body));
        Assert.Equal(HttpStatusCode.UnprocessableEntity, response.StatusCode);
    }

    private static StringContent Json(string json) => new(json, Encoding.UTF8, "application/json");
}
