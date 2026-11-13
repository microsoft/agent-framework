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
    private static readonly DecisionDefinition<LoopVerdict> s_criteria = DecisionDefinition<LoopVerdict>.Create(builder =>
    {
        builder.BinaryProbability(verdict => verdict.BlueSky, "Does `answer` explain why the sky is blue?");
        builder.BinaryProbability(verdict => verdict.RedSunsets, "Does `answer` explain why sunsets are red?");
    });

    [Fact]
    public async Task RunAsync_DelegateEvaluatorWithJev_LoopsUntilEveryCriterionIsMetAsync()
    {
        // Arrange: the first answer misses the sunsets, the second covers both.
        using var answerer = new ScriptedChatClient(
            _ => new ChatResponse(new ChatMessage(ChatRole.Assistant, "Air scatters blue light.")),
            _ => new ChatResponse(new ChatMessage(ChatRole.Assistant, "Air scatters blue light, and sunsets are red because light crosses more air.")));
        using var handler = new JevTestHttpHandler()
            .Reply(HttpStatusCode.OK, JevResultJson.Result(JevResultJson.Noul("blueSky", 0.98), JevResultJson.Noul("redSunsets", 0.03)))
            .Reply(HttpStatusCode.OK, JevResultJson.Result(JevResultJson.Noul("blueSky", 0.97), JevResultJson.Noul("redSunsets", 0.95)));
        using var httpClient = new HttpClient(handler);
        using JevDecisionClient judge = JevDecisionClientTests.CreateClient(httpClient);

        var evaluator = new DelegateLoopEvaluator(async (context, cancellationToken) =>
        {
            string request = string.Join("\n", context.InitialMessages.Select(message => message.Text));
            DecisionResponse<LoopVerdict> decision = await judge.GetResponseAsync(new JudgedAnswer(request, context.LastResponse.Text), s_criteria, cancellationToken: cancellationToken);
            List<string> missing = [];
            if (decision.Result.BlueSky <= 0.5)
            {
                missing.Add("blueSky");
            }

            if (decision.Result.RedSunsets <= 0.5)
            {
                missing.Add("redSunsets");
            }

            return missing.Count == 0 ? LoopEvaluation.Stop() : LoopEvaluation.Continue($"Missing: {string.Join(", ", missing)}.");
        });
        var loop = new LoopAgent(answerer.AsAIAgent(), evaluator, new LoopAgentOptions { MaxIterations = 3, NonStreamingReturnsLastResponseOnly = true });

        // Act
        AgentResponse response = await loop.RunAsync("Explain why the sky is blue and why sunsets are red.");

        // Assert: two runs, and the second run received the missing criterion as feedback.
        Assert.Equal(2, answerer.Calls.Count);
        Assert.Contains(answerer.Calls[1], message => message.Role == ChatRole.User && message.Text == "Missing: redSunsets.");
        Assert.Contains("sunsets are red", response.Text, StringComparison.Ordinal);

        // Assert: Jev judged the original request and the latest answer, with one Noul question per criterion.
        Assert.Equal(2, handler.Requests.Count);
        JsonNode first = JsonNode.Parse(handler.Requests[0].Body)!;
        Assert.Equal(["blueSky", "redSunsets"], first["questions"]!.AsObject().Select(question => question.Key));
        Assert.All(first["questions"]!.AsObject(), question => Assert.Equal("noul", (string?)question.Value!["type"]));
        Assert.Equal("Explain why the sky is blue and why sunsets are red.", (string?)first["state"]!["request"]);
        Assert.Equal("Air scatters blue light.", (string?)first["state"]!["answer"]);
    }
}

public sealed record JudgedAnswer(string Request, string Answer);

public sealed record LoopVerdict(double BlueSky, double RedSunsets);
