// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.Linq;
using System.Net;
using System.Net.Http;
using System.Text.Json;
using System.Text.Json.Nodes;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.Logging;

namespace Microsoft.Agents.AI.TypeSafe.UnitTests;

public sealed class JevChatClientToolTests
{
    private const string Route = JevChatTestData.Route;

    public enum City
    {
        Seattle,
        Paris,
    }

    public enum Unit
    {
        Celsius,
        Fahrenheit,
    }

    public enum Feature
    {
        Wind,
        Humidity,
        Uv,
    }

    [Fact]
    public async Task GetResponseAsync_JevSelectsATool_ReturnsTheFunctionCallAsync()
    {
        // Arrange: city and detailed are required; unit is optional and nullable.
        AIFunction weather = AIFunctionFactory.Create(
            ([Description("The city")] City city, [Description("Include the hourly forecast")] bool detailed, Unit? unit = null) => "sunny",
            "get_weather",
            "Gets the weather for a supported city.");
        using var handler = new JevTestHttpHandler().Reply(HttpStatusCode.OK, JevChatTestData.Result(
            JevChatTestData.UserAnswers(),
            JevChatTestData.RouteTo("t0", "t0", "none"),
            JevChatTestData.Choice("__af_tool__.t0.a0.value", "v1", "v0", "v1"),
            JevChatTestData.Noul("__af_tool__.t0.a1.value", 0.9),
            JevChatTestData.Noul("__af_tool__.t0.a2.present", 0.2),
            JevChatTestData.Choice("__af_tool__.t0.a2.value", "v1", "v0", "v1")));
        using var httpClient = new HttpClient(handler);
        using JevChatClient client = JevChatClientTests.CreateClient(httpClient);

        // Act
        ChatResponse response = await client.GetResponseAsync(JevTestData.TicketText, new ChatOptions { Tools = [weather] }.WithJevQuestions(JevChatTestData.Questions()));

        // Assert: the call has the chosen enum value and Boolean, and leaves out the optional argument.
        FunctionCallContent call = Assert.IsType<FunctionCallContent>(Assert.Single(Assert.Single(response.Messages).Contents));
        Assert.Equal("get_weather", call.Name);
        Assert.StartsWith("typesafe-", call.CallId, StringComparison.Ordinal);
        Assert.Equal(["city", "detailed"], call.Arguments!.Keys.Order());
        Assert.Equal("Paris", Assert.IsType<JsonElement>(call.Arguments["city"]).GetString());
        Assert.True(Assert.IsType<JsonElement>(call.Arguments["detailed"]).GetBoolean());
        Assert.Equal(ChatFinishReason.ToolCalls, response.FinishReason);
        Assert.Null(response.GetJevResult());

        // Assert: the request adds the internal routing questions after the caller's questions.
        JsonObject questions = JsonNode.Parse(Assert.Single(handler.Requests).Body)!["questions"]!.AsObject();
        Assert.Equal(
            ["department", "is_urgent", Route, "__af_tool__.t0.a0.value", "__af_tool__.t0.a1.value", "__af_tool__.t0.a2.present", "__af_tool__.t0.a2.value"],
            questions.Select(question => question.Key));
        Assert.Equal("Tool 'get_weather': Gets the weather for a supported city.", (string?)questions[Route]!["criteria"]!["t0"]);
        Assert.NotNull(questions[Route]!["criteria"]!["none"]);
        Assert.Equal("\"Paris\"", (string?)questions["__af_tool__.t0.a0.value"]!["criteria"]!["v1"]);
        Assert.Equal("noul", (string?)questions["__af_tool__.t0.a1.value"]!["type"]);
        Assert.Contains("did the user explicitly specify the unit argument", (string?)questions["__af_tool__.t0.a2.present"]!["instructions"], StringComparison.Ordinal);
    }

    [Fact]
    public async Task GetResponseAsync_OptionalArgumentPresent_IsPassedAsync()
    {
        // Arrange
        AIFunction weather = AIFunctionFactory.Create((City city, Unit? unit = null, Feature[]? features = null) => "sunny", "get_weather");
        using var handler = new JevTestHttpHandler().Reply(HttpStatusCode.OK, JevChatTestData.Result(
            JevChatTestData.UserAnswers(),
            JevChatTestData.RouteTo("t0", "t0", "none"),
            JevChatTestData.Choice("__af_tool__.t0.a0.value", "v0", "v0", "v1"),
            JevChatTestData.Noul("__af_tool__.t0.a1.present", 0.8),
            JevChatTestData.Choice("__af_tool__.t0.a1.value", "v1", "v0", "v1"),
            JevChatTestData.Noul("__af_tool__.t0.a2.present", 0.7),
            JevChatTestData.Noul("__af_tool__.t0.a2.m0", 0.9),
            JevChatTestData.Noul("__af_tool__.t0.a2.m1", 0.1),
            JevChatTestData.Noul("__af_tool__.t0.a2.m2", 0.6)));
        using var httpClient = new HttpClient(handler);
        using JevChatClient client = JevChatClientTests.CreateClient(httpClient);

        // Act
        ChatResponse response = await client.GetResponseAsync(JevTestData.TicketText, new ChatOptions { Tools = [weather] }.WithJevQuestions(JevChatTestData.Questions()));

        // Assert: a nullable enum is a Choice without null, and an enum array is one Noul per member.
        FunctionCallContent call = response.Messages.SelectMany(message => message.Contents).OfType<FunctionCallContent>().Single();
        Assert.Equal("Seattle", Assert.IsType<JsonElement>(call.Arguments!["city"]).GetString());
        Assert.Equal("Fahrenheit", Assert.IsType<JsonElement>(call.Arguments["unit"]).GetString());
        Assert.Equal(["Wind", "Uv"], Assert.IsType<JsonElement>(call.Arguments["features"]).EnumerateArray().Select(item => item.GetString()));

        JsonObject questions = JsonNode.Parse(Assert.Single(handler.Requests).Body)!["questions"]!.AsObject();
        Assert.Equal(["v0", "v1"], questions["__af_tool__.t0.a1.value"]!["criteria"]!.AsObject().Select(criterion => criterion.Key));
    }

    [Fact]
    public async Task GetResponseAsync_JevChoosesNoTool_ReturnsOnlyTheCallersAnswersAsync()
    {
        // Arrange
        AIFunction weather = AIFunctionFactory.Create((City city) => "sunny", "get_weather");
        using var handler = new JevTestHttpHandler().Reply(HttpStatusCode.OK, JevChatTestData.Result(
            JevChatTestData.UserAnswers(),
            JevChatTestData.RouteTo("none", "t0", "none"),
            JevChatTestData.Choice("__af_tool__.t0.a0.value", "v0", "v0", "v1")));
        using var httpClient = new HttpClient(handler);
        using JevChatClient client = JevChatClientTests.CreateClient(httpClient);

        // Act
        ChatResponse response = await client.GetResponseAsync(JevTestData.TicketText, new ChatOptions { Tools = [weather] }.WithJevQuestions(JevChatTestData.Questions()));

        // Assert
        JevResult result = Assert.IsType<JevResult>(response.GetJevResult());
        Assert.Equal(["department", "is_urgent"], result.Answers.Keys);
        Assert.DoesNotContain("__af_tool__", response.Text, StringComparison.Ordinal);
        Assert.Equal(ChatFinishReason.Stop, response.FinishReason);
    }

    [Fact]
    public async Task GetResponseAsync_AfterTheToolCallLimit_AnswersWithTheToolResultsAsync()
    {
        // Arrange: the turn already has one call and its result, which is the default limit.
        AIFunction weather = AIFunctionFactory.Create((City city) => "sunny", "get_weather");
        using var handler = new JevTestHttpHandler().Reply(HttpStatusCode.OK, JevChatTestData.Result(
            JevChatTestData.UserAnswers(),
            JevChatTestData.Score("severity", 1.5, 3)));
        using var httpClient = new HttpClient(handler);
        using JevChatClient client = JevChatClientTests.CreateClient(httpClient);
        Dictionary<string, JevQuestion> questions = JevChatTestData.Questions();
        questions["severity"] = new JevScoreQuestion { Instructions = "How severe?", Criteria = ["Low", "Medium", "High"] };
        ChatMessage[] messages =
        [
            new(ChatRole.User, "Earlier question"),
            new(ChatRole.Assistant, [new FunctionCallContent("call_0", "get_weather", new Dictionary<string, object?> { ["city"] = "Paris" })]),
            new(ChatRole.Tool, [new FunctionResultContent("call_0", "Paris is cloudy.")]),
            new(ChatRole.Assistant, "Paris is cloudy.\ndepartment: technical"),
            new(ChatRole.User, "Weather in Seattle?"),
            new(ChatRole.Assistant, [new FunctionCallContent("call_1", "get_weather", new Dictionary<string, object?> { ["city"] = "Seattle" })]),
            new(ChatRole.Tool, [new FunctionResultContent("call_1", JsonSerializer.SerializeToElement("Seattle is sunny."))]),
        ];

        // Act
        ChatResponse response = await client.GetResponseAsync(messages, new ChatOptions { Tools = [weather] }.WithJevQuestions(questions));

        // Assert: no tool questions, and the text has this turn's tool result and the Choice and Score decisions.
        Assert.Equal(["department", "is_urgent", "severity"], JsonNode.Parse(Assert.Single(handler.Requests).Body)!["questions"]!.AsObject().Select(question => question.Key));
        Assert.Equal("Seattle is sunny.\ndepartment: technical\nseverity: 1.5", response.Text);
        Assert.NotNull(response.GetJevResult());
    }

    [Fact]
    public async Task GetResponseAsync_HigherLimit_OffersToolsAgainWithHintsAsync()
    {
        // Arrange
        AIFunction weather = AIFunctionFactory.Create((City city) => "sunny", "get_weather", "Gets the weather.");
        using var handler = new JevTestHttpHandler().Reply(HttpStatusCode.OK, JevChatTestData.Result(
            JevChatTestData.UserAnswers(),
            JevChatTestData.RouteTo("t0", "t0", "none"),
            JevChatTestData.Choice("__af_tool__.t0.a0.value", "v1", "v0", "v1")));
        using var httpClient = new HttpClient(handler);
        using JevChatClient client = JevChatClientTests.CreateClient(httpClient, new JevChatClientOptions { MaximumToolCallsPerTurn = 2 });
        ChatMessage[] messages =
        [
            new(ChatRole.User, "Weather in Seattle and Paris?"),
            new(ChatRole.Assistant, [new FunctionCallContent("call_1", "get_weather", new Dictionary<string, object?> { ["city"] = JsonSerializer.SerializeToElement("Seattle") })]),
            new(ChatRole.Tool, [new FunctionResultContent("call_1", "Seattle is sunny.")]),
        ];

        // Act
        ChatResponse response = await client.GetResponseAsync(messages, new ChatOptions { Tools = [weather] }.WithJevQuestions(JevChatTestData.Questions()));

        // Assert: the earlier call becomes a hint in the route and argument questions.
        JsonObject questions = JsonNode.Parse(Assert.Single(handler.Requests).Body)!["questions"]!.AsObject();
        Assert.EndsWith("""Do not repeat argument sets already called this turn: [{"city": "Seattle"}].""", (string?)questions[Route]!["criteria"]!["t0"], StringComparison.Ordinal);
        Assert.Contains("""Values already used for this argument in earlier calls this turn: ["Seattle"].""", (string?)questions["__af_tool__.t0.a0.value"]!["instructions"], StringComparison.Ordinal);
        Assert.Equal("Paris", Assert.IsType<JsonElement>(response.Messages.SelectMany(message => message.Contents).OfType<FunctionCallContent>().Single().Arguments!["city"]).GetString());
    }

    [Fact]
    public async Task GetResponseAsync_UnsupportedTool_IsLeftOutWithAWarningAsync()
    {
        // Arrange: free-form text cannot be chosen from a closed set.
        AIFunction search = AIFunctionFactory.Create((string query) => "found", "search");
        AIFunction weather = AIFunctionFactory.Create((City city) => "sunny", "get_weather");
        using var handler = new JevTestHttpHandler().Reply(HttpStatusCode.OK, JevChatTestData.Result(
            JevChatTestData.UserAnswers(),
            JevChatTestData.RouteTo("none", "t1", "none"),
            JevChatTestData.Choice("__af_tool__.t1.a0.value", "v0", "v0", "v1")));
        using var httpClient = new HttpClient(handler);
        var loggerFactory = new ListLoggerFactory();
        var options = new JevChatClientOptions();
        options.ClientLoggingOptions = new() { LoggerFactory = loggerFactory, EnableLogging = false };
        using JevChatClient client = JevChatClientTests.CreateClient(httpClient, options);

        // Act
        await client.GetResponseAsync(JevTestData.TicketText, new ChatOptions { Tools = [search, weather] }.WithJevQuestions(JevChatTestData.Questions()));

        // Assert: the tools keep their position, so the supported tool is still t1.
        JsonObject criteria = JsonNode.Parse(Assert.Single(handler.Requests).Body)!["questions"]![Route]!["criteria"]!.AsObject();
        Assert.Equal(["t1", "none"], criteria.Select(criterion => criterion.Key));
        (LogLevel level, string message) = Assert.Single(loggerFactory.Entries, entry => entry.Message.Contains("'search'", StringComparison.Ordinal));
        Assert.Equal(LogLevel.Warning, level);
        Assert.Contains("required argument 'query'", message, StringComparison.Ordinal);
    }

    [Fact]
    public async Task GetResponseAsync_RequiredModeWithoutSupportedTools_ThrowsAsync()
    {
        // Arrange
        AIFunction search = AIFunctionFactory.Create((string query) => "found", "search");
        using var handler = new JevTestHttpHandler();
        using var httpClient = new HttpClient(handler);
        using JevChatClient client = JevChatClientTests.CreateClient(httpClient);
        ChatOptions options = new ChatOptions { Tools = [search], ToolMode = ChatToolMode.RequireAny }.WithJevQuestions(JevChatTestData.Questions());

        // Act & Assert
        InvalidOperationException exception = await Assert.ThrowsAsync<InvalidOperationException>(() => client.GetResponseAsync(JevTestData.TicketText, options));
        Assert.Contains("search: required argument 'query'", exception.Message, StringComparison.Ordinal);
        Assert.Empty(handler.Requests);
    }

    [Fact]
    public async Task GetResponseAsync_RequireSpecificTool_SkipsTheRouteQuestionAsync()
    {
        // Arrange
        AIFunction weather = AIFunctionFactory.Create((City city) => "sunny", "get_weather");
        AIFunction forecast = AIFunctionFactory.Create((City city) => "rain", "get_forecast");
        using var handler = new JevTestHttpHandler().Reply(HttpStatusCode.OK, JevChatTestData.Result(
            JevChatTestData.UserAnswers(),
            JevChatTestData.Choice("__af_tool__.t0.a0.value", "v0", "v0", "v1")));
        using var httpClient = new HttpClient(handler);
        using JevChatClient client = JevChatClientTests.CreateClient(httpClient);
        ChatOptions options = new ChatOptions { Tools = [weather, forecast], ToolMode = ChatToolMode.RequireSpecific("get_forecast") }.WithJevQuestions(JevChatTestData.Questions());

        // Act
        ChatResponse response = await client.GetResponseAsync(JevTestData.TicketText, options);

        // Assert
        Assert.Equal("get_forecast", response.Messages.SelectMany(message => message.Contents).OfType<FunctionCallContent>().Single().Name);
        Assert.Null(JsonNode.Parse(Assert.Single(handler.Requests).Body)!["questions"]![Route]);
    }

    [Fact]
    public async Task GetResponseAsync_RequiredModeWithSeveralTools_OmitsTheNoneRouteAsync()
    {
        // Arrange
        AIFunction weather = AIFunctionFactory.Create((City city) => "sunny", "get_weather");
        AIFunction forecast = AIFunctionFactory.Create((City city) => "rain", "get_forecast");
        using var handler = new JevTestHttpHandler().Reply(HttpStatusCode.OK, JevChatTestData.Result(
            JevChatTestData.UserAnswers(),
            JevChatTestData.RouteTo("t1", "t0", "t1"),
            JevChatTestData.Choice("__af_tool__.t0.a0.value", "v0", "v0", "v1"),
            JevChatTestData.Choice("__af_tool__.t1.a0.value", "v1", "v0", "v1")));
        using var httpClient = new HttpClient(handler);
        using JevChatClient client = JevChatClientTests.CreateClient(httpClient);
        ChatOptions options = new ChatOptions { Tools = [weather, forecast], ToolMode = ChatToolMode.RequireAny }.WithJevQuestions(JevChatTestData.Questions());

        // Act
        ChatResponse response = await client.GetResponseAsync(JevTestData.TicketText, options);

        // Assert
        Assert.Equal(["t0", "t1"], JsonNode.Parse(Assert.Single(handler.Requests).Body)!["questions"]![Route]!["criteria"]!.AsObject().Select(criterion => criterion.Key));
        Assert.Equal("get_forecast", response.Messages.SelectMany(message => message.Contents).OfType<FunctionCallContent>().Single().Name);
    }

    [Fact]
    public async Task GetResponseAsync_RequiredToolMissingOrNoneMode_BehaveAsExpectedAsync()
    {
        // Arrange
        AIFunction weather = AIFunctionFactory.Create((City city) => "sunny", "get_weather");
        using var handler = new JevTestHttpHandler().Reply(HttpStatusCode.OK, JevChatTestData.Result(JevChatTestData.UserAnswers()));
        using var httpClient = new HttpClient(handler);
        using JevChatClient client = JevChatClientTests.CreateClient(httpClient);

        // Act & Assert: a missing required tool fails, and the none mode sends only the caller's questions.
        await Assert.ThrowsAsync<InvalidOperationException>(() => client.GetResponseAsync(
            JevTestData.TicketText,
            new ChatOptions { Tools = [weather], ToolMode = ChatToolMode.RequireSpecific("other") }.WithJevQuestions(JevChatTestData.Questions())));
        await client.GetResponseAsync(JevTestData.TicketText, new ChatOptions { Tools = [weather], ToolMode = ChatToolMode.None }.WithJevQuestions(JevChatTestData.Questions()));
        Assert.Equal(["department", "is_urgent"], JsonNode.Parse(Assert.Single(handler.Requests).Body)!["questions"]!.AsObject().Select(question => question.Key));
    }

    [Fact]
    public async Task RunAsync_AgentExecutesTheToolOnce_ThenAnswersAsync()
    {
        // Arrange
        var executions = new List<(City City, bool Detailed)>();
        AIFunction weather = AIFunctionFactory.Create(
            (City city, bool detailed) =>
            {
                executions.Add((city, detailed));
                return $"{city} is sunny{(detailed ? " with an hourly forecast" : string.Empty)}.";
            },
            "get_weather",
            "Gets the weather for a supported city.");
        using var handler = new JevTestHttpHandler()
            .Reply(HttpStatusCode.OK, JevChatTestData.Result(
                JevChatTestData.UserAnswers(),
                JevChatTestData.RouteTo("t0", "t0", "none"),
                JevChatTestData.Choice("__af_tool__.t0.a0.value", "v1", "v0", "v1"),
                JevChatTestData.Noul("__af_tool__.t0.a1.value", 0.9)))
            .Reply(HttpStatusCode.OK, JevChatTestData.Result(JevChatTestData.UserAnswers()));
        using var httpClient = new HttpClient(handler);
        using JevChatClient client = JevChatClientTests.CreateClient(httpClient);
        AIAgent agent = client.AsAIAgent(instructions: "Answer weather requests.", tools: [weather]);

        // Act
        AgentResponse response = await agent.RunAsync(
            "Give me a detailed weather report for Paris.",
            options: new ChatClientAgentRunOptions(new ChatOptions().WithJevQuestions(JevChatTestData.Questions())));

        // Assert: the tool ran once, and the second request answered the caller's questions with its result.
        Assert.Equal([(City.Paris, true)], executions);
        Assert.Equal(2, handler.Requests.Count);
        JsonNode second = JsonNode.Parse(handler.Requests[1].Body)!;
        Assert.Equal(["department", "is_urgent"], second["questions"]!.AsObject().Select(question => question.Key));
        Assert.Equal("Answer weather requests.", (string?)second["state"]!["instructions"]);
        JsonNode toolResult = second["state"]!["messages"]!.AsArray().SelectMany(message => message!["contents"]!.AsArray()).Single(content => (string?)content!["type"] == "function_result")!;
        Assert.Equal("Paris is sunny with an hourly forecast.", (string?)toolResult["result"]);

        Assert.Equal("Paris is sunny with an hourly forecast.\ndepartment: technical", response.Text);
        JevResult result = Assert.IsType<JevResult>(response.GetJevResult());
        Assert.Equal(["department", "is_urgent"], result.Answers.Keys);
        Assert.Equal(24, response.Usage!.TotalTokenCount);
    }

    [Fact]
    public async Task RunAsync_AgentLevelQuestions_AreUsedUnlessTheRunPassesItsOwnAsync()
    {
        // Arrange
        var runQuestions = new Dictionary<string, JevQuestion> { ["spam"] = new JevNoulQuestion { Instructions = "Is it spam?" } };
        using var handler = new JevTestHttpHandler()
            .Reply(HttpStatusCode.OK, JevChatTestData.Result(JevChatTestData.UserAnswers()))
            .Reply(HttpStatusCode.OK, JevChatTestData.Result(JevChatTestData.Noul("spam", 0.05)));
        using var httpClient = new HttpClient(handler);
        using JevChatClient client = JevChatClientTests.CreateClient(httpClient);
        AIAgent agent = client.AsAIAgent(new ChatClientAgentOptions { ChatOptions = new ChatOptions().WithJevQuestions(JevChatTestData.Questions()) });

        // Act
        AgentResponse agentLevel = await agent.RunAsync(JevTestData.TicketText);
        AgentResponse runLevel = await agent.RunAsync(JevTestData.TicketText, options: new ChatClientAgentRunOptions(new ChatOptions().WithJevQuestions(runQuestions)));

        // Assert
        Assert.Equal(["department", "is_urgent"], agentLevel.GetJevResult()!.Answers.Keys);
        Assert.Equal(["spam"], runLevel.GetJevResult()!.Answers.Keys);
    }

    [Fact]
    public async Task RunAsync_ApprovalRequiredTool_RunsOnlyAfterApprovalAsync()
    {
        // Arrange
        int executions = 0;
        AIFunction refund = new ApprovalRequiredAIFunction(AIFunctionFactory.Create(
            (City city) =>
            {
                executions++;
                return "Refund issued.";
            },
            "issue_refund"));
        using var handler = new JevTestHttpHandler()
            .Reply(HttpStatusCode.OK, JevChatTestData.Result(
                JevChatTestData.UserAnswers(),
                JevChatTestData.RouteTo("t0", "t0", "none"),
                JevChatTestData.Choice("__af_tool__.t0.a0.value", "v0", "v0", "v1")))
            .Reply(HttpStatusCode.OK, JevChatTestData.Result(JevChatTestData.UserAnswers("billing")))
            .Reply(HttpStatusCode.OK, JevChatTestData.Result(
                JevChatTestData.UserAnswers("billing"),
                JevChatTestData.RouteTo("none", "t0", "none"),
                JevChatTestData.Choice("__af_tool__.t0.a0.value", "v0", "v0", "v1")));
        using var httpClient = new HttpClient(handler);
        using JevChatClient client = JevChatClientTests.CreateClient(httpClient);
        AIAgent agent = client.AsAIAgent(new ChatClientAgentOptions { ChatOptions = new ChatOptions { Tools = [refund] }.WithJevQuestions(JevChatTestData.Questions()) });
        AgentSession session = await agent.CreateSessionAsync();

        // Act
        AgentResponse pending = await agent.RunAsync("Refund my Seattle order.", session);
        ToolApprovalRequestContent approval = pending.Messages.SelectMany(message => message.Contents).OfType<ToolApprovalRequestContent>().Single();
        int executionsBeforeApproval = executions;
        AgentResponse approved = await agent.RunAsync(new ChatMessage(ChatRole.User, [approval.CreateResponse(true)]), session);
        AgentResponse later = await agent.RunAsync("Thanks. Anything else?", session);

        // Assert
        Assert.Equal(0, executionsBeforeApproval);
        Assert.Equal(1, executions);
        Assert.Equal("Refund issued.\ndepartment: billing", approved.Text);

        // Assert: the next turn still works. The handled approval stays in the history, but Jev does not read it.
        Assert.Equal(3, handler.Requests.Count);
        Assert.DoesNotContain("approval", handler.Requests[2].Body, StringComparison.OrdinalIgnoreCase);
        Assert.NotNull(later.GetJevResult());
    }

    [Fact]
    public async Task RunAsync_ApprovalSentWithText_ContinuesTheTurnOfTheApprovedCallAsync()
    {
        // Arrange
        int executions = 0;
        AIFunction refund = new ApprovalRequiredAIFunction(AIFunctionFactory.Create(
            (City city) =>
            {
                executions++;
                return "Refund issued.";
            },
            "issue_refund"));
        using var handler = new JevTestHttpHandler()
            .Reply(HttpStatusCode.OK, JevChatTestData.Result(
                JevChatTestData.UserAnswers(),
                JevChatTestData.RouteTo("t0", "t0", "none"),
                JevChatTestData.Choice("__af_tool__.t0.a0.value", "v0", "v0", "v1")))
            .Reply(HttpStatusCode.OK, JevChatTestData.Result(JevChatTestData.UserAnswers("billing")));
        using var httpClient = new HttpClient(handler);
        using JevChatClient client = JevChatClientTests.CreateClient(httpClient);
        AIAgent agent = client.AsAIAgent(new ChatClientAgentOptions { ChatOptions = new ChatOptions { Tools = [refund] }.WithJevQuestions(JevChatTestData.Questions()) });
        AgentSession session = await agent.CreateSessionAsync();

        // Act: FunctionInvokingChatClient moves the text after the approved call and its result.
        AgentResponse pending = await agent.RunAsync("Refund my Seattle order.", session);
        ToolApprovalRequestContent approval = pending.Messages.SelectMany(message => message.Contents).OfType<ToolApprovalRequestContent>().Single();
        AgentResponse approved = await agent.RunAsync(new ChatMessage(ChatRole.User, [approval.CreateResponse(true), new TextContent("Yes, go ahead.")]), session);

        // Assert: the approved call counts toward the limit, so the tool is not offered again.
        Assert.Equal(1, executions);
        Assert.Equal(2, handler.Requests.Count);
        Assert.Equal(["department", "is_urgent"], JsonNode.Parse(handler.Requests[1].Body)!["questions"]!.AsObject().Select(question => question.Key));
        Assert.Equal("Refund issued.\ndepartment: billing", approved.Text);
    }

    [Fact]
    public async Task RunStreamingAsync_ThrowsAsync()
    {
        // Arrange
        using var handler = new JevTestHttpHandler();
        using var httpClient = new HttpClient(handler);
        using JevChatClient client = JevChatClientTests.CreateClient(httpClient);
        AIAgent agent = client.AsAIAgent(new ChatClientAgentOptions { ChatOptions = new ChatOptions().WithJevQuestions(JevChatTestData.Questions()) });

        // Act & Assert
        await Assert.ThrowsAsync<NotSupportedException>(async () =>
        {
            await foreach (AgentResponseUpdate update in agent.RunStreamingAsync(JevTestData.TicketText))
            {
            }
        });
        Assert.Empty(handler.Requests);
    }
}
