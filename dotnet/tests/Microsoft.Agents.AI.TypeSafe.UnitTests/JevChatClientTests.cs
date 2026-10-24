// Copyright (c) Microsoft. All rights reserved.

using System;
using System.ClientModel;
using System.ClientModel.Primitives;
using System.Collections.Generic;
using System.Linq;
using System.Net.Http;
using System.Text.Json;
using System.Text.Json.Nodes;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.TypeSafe.UnitTests;

public sealed class JevChatClientTests
{
    private const string Ticket = JevTestData.TicketText;

    [Fact]
    public async Task GetResponseAsync_SendsTheConversationAndQuestions_ReturnsTheTypedResultAsync()
    {
        // Arrange
        using var handler = new JevTestHttpHandler().Reply(System.Net.HttpStatusCode.OK, JevChatTestData.Result(JevChatTestData.UserAnswers()));
        using var httpClient = new HttpClient(handler);
        using JevChatClient client = CreateClient(httpClient);
        ChatMessage[] messages = [new(ChatRole.System, "You triage support tickets."), new(ChatRole.User, Ticket)];

        // Act
        ChatResponse response = await client.GetResponseAsync(messages, new ChatOptions { Instructions = "Be strict." }.WithJevQuestions(JevChatTestData.Questions()));

        // Assert: the request carries the conversation as the state, in the Python connector's shape.
        JevTestHttpHandler.CapturedRequest request = Assert.Single(handler.Requests);
        Assert.Equal(new Uri("https://api.typesafe.ai/v1/systemone"), request.Uri);
        Assert.Equal("test-key", request.Authorization!.Parameter);
        JsonNode body = JsonNode.Parse(request.Body)!;
        Assert.Equal("jev-latest", (string?)body["model"]);
        JsonNode expectedState = JsonNode.Parse($$"""
            {
              "messages": [
                { "role": "system", "contents": [{ "type": "text", "text": "You triage support tickets." }] },
                { "role": "user", "contents": [{ "type": "text", "text": {{JsonSerializer.Serialize(Ticket)}} }] }
              ],
              "instructions": "Be strict."
            }
            """)!;
        Assert.True(JsonNode.DeepEquals(expectedState, body["state"]), body["state"]!.ToJsonString());
        Assert.Equal(["department", "is_urgent"], body["questions"]!.AsObject().Select(question => question.Key));

        // Assert: the text is the result as JSON, and the typed result, usage, and model are on the response.
        JevResult result = Assert.IsType<JevResult>(response.GetJevResult());
        Assert.Equal("technical", Assert.IsType<JevChoiceResponse>(result.Answers["department"]).Choice);
        Assert.Equal(0.9, Assert.IsType<JevNoulResponse>(result.Answers["is_urgent"]).Noul);
        Assert.True(JsonNode.DeepEquals(JsonNode.Parse(response.Text), JsonNode.Parse(JsonSerializer.Serialize(result, JevJsonUtilities.Options))), response.Text);
        Assert.Equal(ChatFinishReason.Stop, response.FinishReason);
        Assert.Equal("jev-test", response.ModelId);
        Assert.Equal(10, response.Usage!.InputTokenCount);
        Assert.Equal(2, response.Usage.OutputTokenCount);
        Assert.Equal(12, response.Usage.TotalTokenCount);
        Assert.Same(result, Assert.Single(response.Messages).RawRepresentation);
    }

    [Fact]
    public async Task GetResponseAsync_ModelIdAndEndpoint_AreUsedAsync()
    {
        // Arrange
        using var handler = new JevTestHttpHandler().Reply(System.Net.HttpStatusCode.OK, JevChatTestData.Result(JevChatTestData.UserAnswers()));
        using var httpClient = new HttpClient(handler);
        using JevChatClient client = CreateClient(httpClient, new JevChatClientOptions { ModelId = "jev-1.13", Endpoint = new Uri("https://proxy.contoso.com/jev") });

        // Act
        await client.GetResponseAsync(Ticket, new ChatOptions { ModelId = "jev-1.14" }.WithJevQuestions(JevChatTestData.Questions()));

        // Assert: a request's model wins over the client's.
        JevTestHttpHandler.CapturedRequest request = Assert.Single(handler.Requests);
        Assert.Equal(new Uri("https://proxy.contoso.com/jev"), request.Uri);
        Assert.Equal("jev-1.14", (string?)JsonNode.Parse(request.Body)!["model"]);

        ChatClientMetadata metadata = Assert.IsType<ChatClientMetadata>(client.GetService(typeof(ChatClientMetadata)));
        Assert.Equal("typesafe.ai", metadata.ProviderName);
        Assert.Equal(new Uri("https://proxy.contoso.com/jev"), metadata.ProviderUri);
        Assert.Equal("jev-1.13", metadata.DefaultModelId);
        Assert.Same(client, client.GetService(typeof(JevChatClient)));
        Assert.Null(client.GetService(typeof(JevChatClient), "key"));
    }

    [Fact]
    public async Task GetResponseAsync_DefaultQuestions_AnswerRequestsWithoutQuestionsAsync()
    {
        // Arrange
        using var handler = new JevTestHttpHandler().Reply(System.Net.HttpStatusCode.OK, JevChatTestData.Result(JevChatTestData.UserAnswers()));
        using var httpClient = new HttpClient(handler);
        using JevChatClient client = CreateClient(httpClient, new JevChatClientOptions { DefaultQuestions = JevChatTestData.Questions() });

        // Act
        ChatResponse response = await client.GetResponseAsync(Ticket);

        // Assert
        Assert.Equal(["department", "is_urgent"], JsonNode.Parse(Assert.Single(handler.Requests).Body)!["questions"]!.AsObject().Select(question => question.Key));
        Assert.NotNull(response.GetJevResult());
    }

    [Fact]
    public async Task GetResponseAsync_RequestQuestions_ReplaceTheDefaultsAsync()
    {
        // Arrange
        using var handler = new JevTestHttpHandler().Reply(System.Net.HttpStatusCode.OK, JevChatTestData.Result(JevChatTestData.Noul("spam", 0.1)));
        using var httpClient = new HttpClient(handler);
        using JevChatClient client = CreateClient(httpClient, new JevChatClientOptions { DefaultQuestions = JevChatTestData.Questions() });
        var questions = new Dictionary<string, JevQuestion> { ["spam"] = new JevNoulQuestion { Instructions = "Is it spam?" } };

        // Act
        await client.GetResponseAsync(Ticket, new ChatOptions().WithJevQuestions(questions));

        // Assert
        Assert.Equal(["spam"], JsonNode.Parse(Assert.Single(handler.Requests).Body)!["questions"]!.AsObject().Select(question => question.Key));
    }

    [Fact]
    public async Task GetResponseAsync_NoQuestions_ThrowsAsync()
    {
        // Arrange
        using var handler = new JevTestHttpHandler();
        using var httpClient = new HttpClient(handler);
        using JevChatClient client = CreateClient(httpClient);

        // Act & Assert
        InvalidOperationException exception = await Assert.ThrowsAsync<InvalidOperationException>(() => client.GetResponseAsync(Ticket));
        Assert.Contains(nameof(JevChatOptionsExtensions.WithJevQuestions), exception.Message, StringComparison.Ordinal);
        await Assert.ThrowsAsync<ArgumentException>(() => client.GetResponseAsync(Ticket, new ChatOptions().WithJevQuestions(new Dictionary<string, JevQuestion>())));
        Assert.Empty(handler.Requests);
    }

    [Fact]
    public async Task GetResponseAsync_ReservedQuestionId_ThrowsAsync()
    {
        // Arrange
        using var handler = new JevTestHttpHandler();
        using var httpClient = new HttpClient(handler);
        using JevChatClient client = CreateClient(httpClient);
        var questions = new Dictionary<string, JevQuestion> { ["__af_tool__.mine"] = new JevNoulQuestion { Instructions = "Yes?" } };

        // Act & Assert
        ArgumentException exception = await Assert.ThrowsAsync<ArgumentException>(() => client.GetResponseAsync(Ticket, new ChatOptions().WithJevQuestions(questions)));
        Assert.Contains("__af_tool__.mine", exception.Message, StringComparison.Ordinal);
        Assert.Empty(handler.Requests);
    }

    [Fact]
    public async Task GetResponseAsync_InvalidQuestion_ThrowsBeforeSendingAsync()
    {
        // Arrange
        using var handler = new JevTestHttpHandler();
        using var httpClient = new HttpClient(handler);
        using JevChatClient client = CreateClient(httpClient);
        var questions = new Dictionary<string, JevQuestion> { ["level"] = new JevScoreQuestion { Instructions = "How bad?", Criteria = ["only one"] } };

        // Act & Assert
        await Assert.ThrowsAsync<ArgumentException>(() => client.GetResponseAsync(Ticket, new ChatOptions().WithJevQuestions(questions)));
        Assert.Empty(handler.Requests);
    }

    public static TheoryData<string, ChatOptions> UnsupportedOptions() => new()
    {
        { nameof(ChatOptions.Temperature), new ChatOptions { Temperature = 0.2f } },
        { nameof(ChatOptions.TopP), new ChatOptions { TopP = 0.5f } },
        { nameof(ChatOptions.TopK), new ChatOptions { TopK = 3 } },
        { nameof(ChatOptions.MaxOutputTokens), new ChatOptions { MaxOutputTokens = 100 } },
        { nameof(ChatOptions.FrequencyPenalty), new ChatOptions { FrequencyPenalty = 0.1f } },
        { nameof(ChatOptions.PresencePenalty), new ChatOptions { PresencePenalty = 0.1f } },
        { nameof(ChatOptions.Seed), new ChatOptions { Seed = 7 } },
        { nameof(ChatOptions.Reasoning), new ChatOptions { Reasoning = new ReasoningOptions() } },
        { nameof(ChatOptions.StopSequences), new ChatOptions { StopSequences = ["stop"] } },
        { nameof(ChatOptions.ResponseFormat), new ChatOptions { ResponseFormat = ChatResponseFormat.Json } },
        { nameof(ChatOptions.ConversationId), new ChatOptions { ConversationId = "conv_1" } },
        { nameof(ChatOptions.AllowBackgroundResponses), new ChatOptions { AllowBackgroundResponses = true } },
        { nameof(ChatOptions.AllowMultipleToolCalls), new ChatOptions { AllowMultipleToolCalls = true } },
        { "HostedWebSearchTool", new ChatOptions { Tools = [new HostedWebSearchTool()] } },
    };

    [Theory]
    [MemberData(nameof(UnsupportedOptions))]
    public async Task GetResponseAsync_UnsupportedOption_ThrowsBeforeSendingAsync(string option, ChatOptions options)
    {
        // Arrange
        using var handler = new JevTestHttpHandler();
        using var httpClient = new HttpClient(handler);
        using JevChatClient client = CreateClient(httpClient);

        // Act & Assert
        NotSupportedException exception = await Assert.ThrowsAsync<NotSupportedException>(() => client.GetResponseAsync(Ticket, options.WithJevQuestions(JevChatTestData.Questions())));
        Assert.Contains(option == "HostedWebSearchTool" ? "web_search" : option, exception.Message, StringComparison.Ordinal);
        Assert.Empty(handler.Requests);
    }

    [Fact]
    public async Task GetResponseAsync_TextResponseFormatAndSingleToolCalls_AreAllowedAsync()
    {
        // Arrange
        using var handler = new JevTestHttpHandler().Reply(System.Net.HttpStatusCode.OK, JevChatTestData.Result(JevChatTestData.UserAnswers()));
        using var httpClient = new HttpClient(handler);
        using JevChatClient client = CreateClient(httpClient);
        var options = new ChatOptions { ResponseFormat = ChatResponseFormat.Text, AllowMultipleToolCalls = false, AllowBackgroundResponses = false, StopSequences = [] };

        // Act
        ChatResponse response = await client.GetResponseAsync(Ticket, options.WithJevQuestions(JevChatTestData.Questions()));

        // Assert
        Assert.NotNull(response.GetJevResult());
    }

    [Fact]
    public async Task GetResponseAsync_NonTextContent_ThrowsBeforeSendingAsync()
    {
        // Arrange
        using var handler = new JevTestHttpHandler();
        using var httpClient = new HttpClient(handler);
        using JevChatClient client = CreateClient(httpClient);
        var message = new ChatMessage(ChatRole.User, [new TextContent("See the screenshot."), new DataContent(new byte[] { 1, 2, 3 }, "image/png")]);

        // Act & Assert
        NotSupportedException exception = await Assert.ThrowsAsync<NotSupportedException>(() => client.GetResponseAsync([message], new ChatOptions().WithJevQuestions(JevChatTestData.Questions())));
        Assert.Contains(nameof(DataContent), exception.Message, StringComparison.Ordinal);
        Assert.Empty(handler.Requests);
    }

    [Fact]
    public async Task GetResponseAsync_EmptyConversation_ThrowsBeforeSendingAsync()
    {
        // Arrange
        using var handler = new JevTestHttpHandler();
        using var httpClient = new HttpClient(handler);
        using JevChatClient client = CreateClient(httpClient);

        // Act & Assert
        await Assert.ThrowsAsync<ArgumentException>(() => client.GetResponseAsync([new ChatMessage(ChatRole.User, "")], new ChatOptions().WithJevQuestions(JevChatTestData.Questions())));
        Assert.Empty(handler.Requests);
    }

    [Fact]
    public async Task GetResponseAsync_ReasoningAndFunctionContent_AreSerializedAsync()
    {
        // Arrange
        using var handler = new JevTestHttpHandler().Reply(System.Net.HttpStatusCode.OK, JevChatTestData.Result(JevChatTestData.UserAnswers()));
        using var httpClient = new HttpClient(handler);
        using JevChatClient client = CreateClient(httpClient);
        ChatMessage[] messages =
        [
            new(ChatRole.User, Ticket),
            new(ChatRole.Assistant, [new TextReasoningContent("Check the order first.") { ProtectedData = "opaque" }, new FunctionCallContent("call_1", "lookup_order", new Dictionary<string, object?> { ["order"] = "A-1" })]),
            new(ChatRole.Tool, [new FunctionResultContent("call_1", JsonSerializer.SerializeToElement("""{"result":"Order A-1 shipped."}"""))]),
            new(ChatRole.Tool, [new FunctionResultContent("call_2", new TextContent("Refund issued."))]),
        ];

        // Act
        await client.GetResponseAsync(messages, new ChatOptions().WithJevQuestions(JevChatTestData.Questions()));

        // Assert: protected reasoning stays out of the state, and rich results become text items.
        JsonNode state = JsonNode.Parse(Assert.Single(handler.Requests).Body)!["state"]!;
        JsonNode expected = JsonNode.Parse("""
            [
              { "type": "text_reasoning", "text": "Check the order first." },
              { "type": "function_call", "call_id": "call_1", "name": "lookup_order", "arguments": { "order": "A-1" } }
            ]
            """)!;
        Assert.True(JsonNode.DeepEquals(expected, state["messages"]![1]!["contents"]), state.ToJsonString());
        Assert.Equal("tool", (string?)state["messages"]![2]!["role"]);
        Assert.Equal("""{"result":"Order A-1 shipped."}""", (string?)state["messages"]![2]!["contents"]![0]!["result"]);
        JsonNode rich = JsonNode.Parse("""{ "type": "function_result", "call_id": "call_2", "result": "Refund issued.", "items": [{ "type": "text", "text": "Refund issued." }] }""")!;
        Assert.True(JsonNode.DeepEquals(rich, state["messages"]![3]!["contents"]![0]), state.ToJsonString());
    }

    [Fact]
    public async Task GetResponseAsync_RichFunctionResult_ThrowsBeforeSendingAsync()
    {
        // Arrange
        using var handler = new JevTestHttpHandler();
        using var httpClient = new HttpClient(handler);
        using JevChatClient client = CreateClient(httpClient);
        ChatMessage[] messages =
        [
            new(ChatRole.User, Ticket),
            new(ChatRole.Tool, [new FunctionResultContent("call_1", new DataContent(new byte[] { 1 }, "image/png"))]),
        ];

        // Act & Assert
        await Assert.ThrowsAsync<NotSupportedException>(() => client.GetResponseAsync(messages, new ChatOptions().WithJevQuestions(JevChatTestData.Questions())));
        Assert.Empty(handler.Requests);
    }

    [Fact]
    public async Task GetResponseAsync_ResultMissingAnAnswer_ThrowsAsync()
    {
        // Arrange
        using var handler = new JevTestHttpHandler().Reply(System.Net.HttpStatusCode.OK, JevChatTestData.Result(JevChatTestData.Noul("is_urgent", 0.9)));
        using var httpClient = new HttpClient(handler);
        using JevChatClient client = CreateClient(httpClient);

        // Act & Assert
        InvalidOperationException exception = await Assert.ThrowsAsync<InvalidOperationException>(() => client.GetResponseAsync(Ticket, new ChatOptions().WithJevQuestions(JevChatTestData.Questions())));
        Assert.Contains("department", exception.Message, StringComparison.Ordinal);
    }

    [Fact]
    public async Task GetResponseAsync_ApiError_ThrowsClientResultExceptionAsync()
    {
        // Arrange
        using var handler = new JevTestHttpHandler().Reply(System.Net.HttpStatusCode.UnprocessableEntity, """{"detail":"questions.department.criteria: Field required"}""");
        using var httpClient = new HttpClient(handler);
        using JevChatClient client = CreateClient(httpClient);

        // Act & Assert
        ClientResultException exception = await Assert.ThrowsAsync<ClientResultException>(() => client.GetResponseAsync(Ticket, new ChatOptions().WithJevQuestions(JevChatTestData.Questions())));
        Assert.Equal(422, exception.Status);
        Assert.Contains("Field required", exception.Message, StringComparison.Ordinal);
    }

    [Fact]
    public async Task GetStreamingResponseAsync_ThrowsAsync()
    {
        // Arrange
        using var handler = new JevTestHttpHandler();
        using var httpClient = new HttpClient(handler);
        using JevChatClient client = CreateClient(httpClient);

        // Act & Assert
        await Assert.ThrowsAsync<NotSupportedException>(async () =>
        {
            await foreach (ChatResponseUpdate update in client.GetStreamingResponseAsync(Ticket, new ChatOptions().WithJevQuestions(JevChatTestData.Questions())))
            {
            }
        });
        Assert.Empty(handler.Requests);
    }

    [Fact]
    public void Constructor_InvalidOptions_Throw()
    {
        Assert.Throws<ArgumentException>(() => new JevChatClient(new ApiKeyCredential("k"), new JevChatClientOptions { ModelId = " " }));
        Assert.Throws<ArgumentException>(() => new JevChatClient(new ApiKeyCredential("k"), new JevChatClientOptions { Endpoint = new Uri("/relative", UriKind.Relative) }));
        Assert.Throws<ArgumentOutOfRangeException>(() => new JevChatClientOptions { MaximumToolCallsPerTurn = -1 });
    }

    [Fact]
    public void Constructor_FreezesTheOptions()
    {
        // Arrange
        var options = new JevChatClientOptions();

        // Act
        using var client = new JevChatClient(new ApiKeyCredential("k"), options);

        // Assert: like other client options, the options are read-only once used.
        Assert.Throws<InvalidOperationException>(() => options.ModelId = "other");
        Assert.Throws<InvalidOperationException>(() => options.DefaultQuestions = JevChatTestData.Questions());
        Assert.IsType<JevRetryPolicy>(options.RetryPolicy);
        Assert.Equal(TimeSpan.FromSeconds(10), options.NetworkTimeout);
    }

    [Fact]
    public void WithJevQuestions_OtherClients_KeepThePreviousFactory()
    {
        // Arrange
        using var handler = new JevTestHttpHandler();
        using var httpClient = new HttpClient(handler);
        using JevChatClient jev = CreateClient(httpClient);
        using var other = new ScriptedChatClient();
        object otherOptions = new();
        var options = new ChatOptions { RawRepresentationFactory = _ => otherOptions };

        // Act
        options.WithJevQuestions(JevChatTestData.Questions());

        // Assert
        Assert.Same(otherOptions, options.RawRepresentationFactory!(other));
        Assert.Equal(["department", "is_urgent"], Assert.IsType<JevChatRequestOptions>(options.RawRepresentationFactory(jev)).Questions.Keys);
    }

    internal static JevChatClient CreateClient(HttpClient httpClient, JevChatClientOptions? options = null)
    {
        options ??= new JevChatClientOptions();
        options.Transport = new HttpClientPipelineTransport(httpClient);
        options.RetryPolicy = new JevRetryPolicy { RecordedWaitsForTests = [] };
        return new JevChatClient(new ApiKeyCredential("test-key"), options);
    }
}
