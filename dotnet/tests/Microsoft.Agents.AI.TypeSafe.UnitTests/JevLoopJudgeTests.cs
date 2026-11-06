// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Net;
using System.Net.Http;
using System.Text.Json.Nodes;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;

#pragma warning disable MAAI001 // LoopAgent and its evaluators are experimental.

namespace Microsoft.Agents.AI.TypeSafe.UnitTests;

/// <summary>
/// Tests Jev as the judge of a <see cref="LoopAgent"/>, as the loop judge sample does.
/// </summary>
public sealed class JevLoopJudgeTests
{
    private static readonly Dictionary<string, JevQuestion> s_criteria = new()
    {
        ["blue_sky"] = new JevNoulQuestion { Instructions = "Does the assistant's latest response explain why the sky is blue?" },
        ["red_sunsets"] = new JevNoulQuestion { Instructions = "Does the assistant's latest response explain why sunsets are red?" },
    };

    [Fact]
    public async Task RunAsync_DelegateEvaluatorWithJev_LoopsUntilEveryCriterionIsMetAsync()
    {
        // Arrange: the first answer misses the sunsets, the second covers both.
        using var answerer = new ScriptedChatClient(
            _ => new ChatResponse(new ChatMessage(ChatRole.Assistant, "Air scatters blue light.")),
            _ => new ChatResponse(new ChatMessage(ChatRole.Assistant, "Air scatters blue light, and sunsets are red because light crosses more air.")));
        using var handler = new JevTestHttpHandler()
            .Reply(HttpStatusCode.OK, JevChatTestData.Result(JevChatTestData.Noul("blue_sky", 0.98), JevChatTestData.Noul("red_sunsets", 0.03)))
            .Reply(HttpStatusCode.OK, JevChatTestData.Result(JevChatTestData.Noul("blue_sky", 0.97), JevChatTestData.Noul("red_sunsets", 0.95)));
        using var httpClient = new HttpClient(handler);
        using JevChatClient judge = JevChatClientTests.CreateClient(httpClient);

        var evaluator = new DelegateLoopEvaluator(async (context, cancellationToken) =>
        {
            List<ChatMessage> conversation = [.. context.InitialMessages, new ChatMessage(ChatRole.Assistant, context.LastResponse.Text)];
            ChatResponse verdict = await judge.GetResponseAsync(conversation, new ChatOptions().WithJevQuestions(s_criteria), cancellationToken);
            List<string> missing = [.. verdict.GetJevResult()!.Answers.Where(answer => ((JevNoulResponse)answer.Value).Noul <= 0.5).Select(answer => answer.Key)];
            return missing.Count == 0 ? LoopEvaluation.Stop() : LoopEvaluation.Continue($"Missing: {string.Join(", ", missing)}.");
        });
        var loop = new LoopAgent(answerer.AsAIAgent(), evaluator, new LoopAgentOptions { MaxIterations = 3, NonStreamingReturnsLastResponseOnly = true });

        // Act
        AgentResponse response = await loop.RunAsync("Explain why the sky is blue and why sunsets are red.");

        // Assert: two runs, and the second run received the missing criterion as feedback.
        Assert.Equal(2, answerer.Calls.Count);
        Assert.Contains(answerer.Calls[1], message => message.Role == ChatRole.User && message.Text == "Missing: red_sunsets.");
        Assert.Contains("sunsets are red", response.Text, StringComparison.Ordinal);

        // Assert: Jev read the original request and the latest answer, and only the criteria questions.
        Assert.Equal(2, handler.Requests.Count);
        JsonNode first = JsonNode.Parse(handler.Requests[0].Body)!;
        Assert.Equal(["blue_sky", "red_sunsets"], first["questions"]!.AsObject().Select(question => question.Key));
        JsonArray messages = first["state"]!["messages"]!.AsArray();
        Assert.Equal(["user", "assistant"], messages.Select(message => (string?)message!["role"]));
        Assert.Equal("Air scatters blue light.", (string?)messages[1]!["contents"]![0]!["text"]);
    }

    [Fact]
    public async Task EvaluateAsync_AIJudgeLoopEvaluatorWithJev_IsNotSupportedAsync()
    {
        // Arrange: AIJudgeLoopEvaluator asks for a JudgeVerdict as JSON structured output, which Jev cannot write.
        using var handler = new JevTestHttpHandler();
        using var httpClient = new HttpClient(handler);
        using JevChatClient judge = JevChatClientTests.CreateClient(httpClient, new JevChatClientOptions { DefaultQuestions = s_criteria });
        using var answerer = new ScriptedChatClient(_ => new ChatResponse(new ChatMessage(ChatRole.Assistant, "Air scatters blue light.")));
        var loop = new LoopAgent(answerer.AsAIAgent(), new AIJudgeLoopEvaluator(judge));

        // Act & Assert: the request fails before anything is sent, which is why the sample uses a delegate evaluator.
        NotSupportedException exception = await Assert.ThrowsAsync<NotSupportedException>(() => loop.RunAsync("Why is the sky blue?"));
        Assert.Contains(nameof(ChatOptions.ResponseFormat), exception.Message, StringComparison.Ordinal);
        Assert.Empty(handler.Requests);
    }
}
