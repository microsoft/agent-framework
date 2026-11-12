// Copyright (c) Microsoft. All rights reserved.

using System;
using System.ClientModel;
using System.ClientModel.Primitives;
using System.Collections.Generic;
using System.Linq;
using System.Net;
using System.Net.Http;
using System.Text.Json;
using System.Text.Json.Nodes;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.TypeSafe.UnitTests;

/// <summary>
/// Tests <see cref="JevDecisionClient"/>, which answers provider-neutral decision requests with Jev.
/// </summary>
public sealed class JevDecisionClientTests
{
    private static readonly JsonElement s_state = JsonDocument.Parse("""{ "ticket": "I was charged twice." }""").RootElement.Clone();

    [Fact]
    public async Task GetResponseAsync_DecisionQuestions_AreAskedAsJevQuestionsAsync()
    {
        // Arrange
        using var handler = new JevTestHttpHandler().Reply(HttpStatusCode.OK, JevChatTestData.Result(
            JevChatTestData.Noul("refund", 0.95),
            "\"department\":{\"type\":\"choice\",\"choice\":\"billing\",\"confidence\":0.8,\"probabilities\":{\"technical\":0.1,\"billing\":0.9}}",
            JevChatTestData.Score("severity", 1.5, 3)));
        using var httpClient = new HttpClient(handler);
        using JevDecisionClient client = CreateClient(httpClient);
        var request = new DecisionRequest(s_state, [
            new BinaryDecisionQuestion("refund", "Does the customer ask for a refund?", trueDescription: "A refund or reversal is requested."),
            new ChoiceDecisionQuestion("department", "Which team should handle it?", [new("billing", "Payments"), new("technical", "Bugs")]),
            new ScoreDecisionQuestion("severity", null, [new("cosmetic", "Cosmetic"), new("workaround", "Workaround available"), new("blocked", "Fully blocked")]),
        ]);

        // Act
        DecisionResponse response = await client.GetResponseAsync(request);

        // Assert: the request is the Jev wire shape, with the Score rubric in level order.
        JsonNode expected = JsonNode.Parse("""
            {
              "state": { "ticket": "I was charged twice." },
              "model": "jev-test",
              "questions": {
                "refund": { "type": "noul", "instructions": "Does the customer ask for a refund?", "criteria": { "true": "A refund or reversal is requested." } },
                "department": { "type": "choice", "instructions": "Which team should handle it?", "criteria": { "billing": "Payments", "technical": "Bugs" } },
                "severity": { "type": "score", "criteria": ["Cosmetic", "Workaround available", "Fully blocked"] }
              }
            }
            """)!;
        string body = Assert.Single(handler.Requests).Body;
        Assert.True(JsonNode.DeepEquals(expected, JsonNode.Parse(body)), body);

        // Assert: the answers are in request order, keyed by the caller's IDs, with Jev's values and confidence.
        Assert.Equal(0.95, Assert.IsType<BinaryDecisionAnswer>(response.Answers[0]).TrueProbability);
        ChoiceDecisionAnswer department = Assert.IsType<ChoiceDecisionAnswer>(response.Answers[1]);
        Assert.Equal("billing", department.SelectedCandidateId);
        Assert.Equal([("billing", 0.9), ("technical", 0.1)], department.Probabilities.Select(probability => (probability.Id, probability.Value)));
        Assert.Equal(0.8, department.AdditionalProperties![JevDecisionMapping.ConfidenceProperty]);
        Assert.IsType<JevChoiceResponse>(department.RawRepresentation);
        ScoreDecisionAnswer severity = Assert.IsType<ScoreDecisionAnswer>(response.Answers[2]);
        Assert.Equal(1.5, severity.Score);
        Assert.Equal(1.5, severity.ExpectedScore, 6);
        Assert.Equal(["cosmetic", "workaround", "blocked"], severity.Probabilities.Select(probability => probability.Id));
        Assert.Equal([0.0, 0.5, 0.5], severity.Probabilities.Select(probability => probability.Value));

        // Assert: the provenance, usage, and raw result.
        Assert.Equal(JevDecisionClient.ProviderName, response.Provenance!.ProviderName);
        Assert.Equal("jev-test", response.Provenance.ModelId);
        Assert.Equal(DecisionPrecision.TwoDecimalPlaces, response.Provenance.Precision);
        Assert.All(response.Answers, answer => Assert.Equal(DecisionPrecision.TwoDecimalPlaces, answer.Precision));
        Assert.Equal(12, response.Usage!.TotalTokenCount);
        Assert.IsType<JevResult>(response.RawRepresentation);
    }

    [Fact]
    public async Task GetResponseAsync_JevQuestionsInRawOptions_AreSentUnchangedAsync()
    {
        // Arrange: JSON instructions and an undescribed label, which decision questions cannot carry as they are.
        using var handler = new JevTestHttpHandler().Reply(HttpStatusCode.OK, JevChatTestData.Result(JevChatTestData.Choice("duplicate", "yes", "yes", "no")));
        using var httpClient = new HttpClient(handler);
        using JevDecisionClient client = CreateClient(httpClient);
        JsonElement instructions = JsonDocument.Parse("""{ "question": "Is the resume for the same person as `candidate`?", "candidate": { "name": "Ana" } }""").RootElement.Clone();
        var jevQuestions = new Dictionary<string, JevQuestion>
        {
            ["duplicate"] = new JevChoiceQuestion { Instructions = (JevEntry)instructions, Criteria = new Dictionary<string, JevEntry> { ["yes"] = JevEntry.Null, ["no"] = "A different person" } },
        };
        DecisionQuestion question = JevDecisionMapping.ToDecisionQuestion("duplicate", jevQuestions["duplicate"]);
        var options = new DecisionOptions { RawRepresentationFactory = _ => new JevDecisionRequestOptions { Questions = jevQuestions } };

        // Act
        DecisionResponse response = await client.GetResponseAsync(new DecisionRequest(s_state, [question]), options);

        // Assert
        JsonNode sent = JsonNode.Parse(Assert.Single(handler.Requests).Body)!["questions"]!["duplicate"]!;
        Assert.True(JsonNode.DeepEquals(JsonNode.Parse(instructions.GetRawText()), sent["instructions"]), sent.ToJsonString());
        Assert.Null(sent["criteria"]!["yes"]);
        Assert.Equal("yes", Assert.IsType<ChoiceDecisionAnswer>(Assert.Single(response.Answers)).SelectedCandidateId);
    }

    [Fact]
    public async Task GetResponseAsync_IncompleteDistribution_ThrowsDecisionProtocolExceptionAsync()
    {
        // Arrange: the answer leaves out a label, so its distribution is not complete.
        using var handler = new JevTestHttpHandler().Reply(HttpStatusCode.OK, JevChatTestData.Result(
            "\"department\":{\"type\":\"choice\",\"choice\":\"billing\",\"confidence\":0.9,\"probabilities\":{\"billing\":1.0}}"));
        using var httpClient = new HttpClient(handler);
        using JevDecisionClient client = CreateClient(httpClient);
        var request = new DecisionRequest(s_state, [new ChoiceDecisionQuestion("department", "Which team?", [new("billing", "Payments"), new("technical", "Bugs")])]);

        // Act & Assert
        DecisionProtocolException exception = await Assert.ThrowsAsync<DecisionProtocolException>(() => client.GetResponseAsync(request));
        Assert.Contains("'technical'", exception.Message, StringComparison.Ordinal);
    }

    [Fact]
    public async Task GetResponseAsync_DistributionRoundedToTwoDecimals_IsAcceptedAsync()
    {
        // Arrange: Jev rounds to two decimals, so three even probabilities sum to 0.99 rather than 1.
        using var handler = new JevTestHttpHandler().Reply(HttpStatusCode.OK, JevChatTestData.Result(
            "\"department\":{\"type\":\"choice\",\"choice\":\"billing\",\"confidence\":0.01,\"probabilities\":{\"billing\":0.33,\"technical\":0.33,\"sales\":0.33}}"));
        using var httpClient = new HttpClient(handler);
        using JevDecisionClient client = CreateClient(httpClient);
        var request = new DecisionRequest(s_state, [new ChoiceDecisionQuestion("department", "Which team?", [new("billing", "Payments"), new("technical", "Bugs"), new("sales", "Plans")])]);

        // Act
        DecisionResponse response = await client.GetResponseAsync(request);

        // Assert: the observed values are kept as reported.
        ChoiceDecisionAnswer answer = Assert.IsType<ChoiceDecisionAnswer>(Assert.Single(response.Answers));
        Assert.Equal([0.33, 0.33, 0.33], answer.Probabilities.Select(probability => probability.Value));
    }

    [Fact]
    public async Task GetResponseAsync_ValueWithinRoundingErrorOfItsBound_IsMovedOntoTheBoundAsync()
    {
        // Arrange
        using var handler = new JevTestHttpHandler().Reply(HttpStatusCode.OK, JevChatTestData.Result(JevChatTestData.Noul("refund", 1.0000001)));
        using var httpClient = new HttpClient(handler);
        using JevDecisionClient client = CreateClient(httpClient);

        // Act
        DecisionResponse response = await client.GetResponseAsync(new DecisionRequest(s_state, [new BinaryDecisionQuestion("refund", "Refund?")]));

        // Assert
        Assert.Equal(1.0, Assert.IsType<BinaryDecisionAnswer>(Assert.Single(response.Answers)).TrueProbability);
    }

    [Fact]
    public async Task GetResponseAsync_StateThatIsNotTextObjectOrArray_ThrowsBeforeSendingAsync()
    {
        // Arrange
        using var handler = new JevTestHttpHandler();
        using var httpClient = new HttpClient(handler);
        using JevDecisionClient client = CreateClient(httpClient);
        JsonElement number = JsonDocument.Parse("5").RootElement.Clone();

        // Act & Assert
        await Assert.ThrowsAsync<ArgumentException>(() => client.GetResponseAsync(new DecisionRequest(number, [new BinaryDecisionQuestion("refund", "Refund?")])));
        Assert.Empty(handler.Requests);
    }

    [Fact]
    public async Task GetResponseAsync_ModelInOptions_WinsOverTheClientModelAsync()
    {
        // Arrange
        using var handler = new JevTestHttpHandler().Reply(HttpStatusCode.OK, JevChatTestData.Result(JevChatTestData.Noul("refund", 0.5)));
        using var httpClient = new HttpClient(handler);
        using JevDecisionClient client = CreateClient(httpClient);

        // Act
        await client.GetResponseAsync(new DecisionRequest(s_state, [new BinaryDecisionQuestion("refund", "Refund?")]), new DecisionOptions { ModelId = "jev-1.14" });

        // Assert
        Assert.Equal("jev-1.14", (string?)JsonNode.Parse(Assert.Single(handler.Requests).Body)!["model"]);
    }

    [Fact]
    public void GetService_ReturnsTheMetadataAndTheClient()
    {
        // Arrange
        using var httpClient = new HttpClient(new JevTestHttpHandler());
        using JevDecisionClient client = CreateClient(httpClient);

        // Act
        DecisionClientMetadata? metadata = client.GetService<DecisionClientMetadata>();

        // Assert
        Assert.Equal(JevDecisionClient.ProviderName, metadata!.ProviderName);
        Assert.Equal("jev-test", metadata.DefaultModelId);
        Assert.Equal([DecisionKind.Binary, DecisionKind.Choice, DecisionKind.Score], metadata.SupportedKinds);
        Assert.Same(client, client.GetService<IDecisionClient>());
        Assert.Null(client.GetService<DecisionClientMetadata>("key"));
    }

    [Fact]
    public void ToDecisionQuestion_NoulWithOneCriterion_UsesItAsTheInstructions()
    {
        // Arrange: Jev accepts a Noul with only one outcome described, which a Binary question cannot express directly.
        var noul = new JevNoulQuestion { Criteria = new JevNoulCriteria { True = "The customer is angry." } };

        // Act
        BinaryDecisionQuestion question = Assert.IsType<BinaryDecisionQuestion>(JevDecisionMapping.ToDecisionQuestion("angry", noul));

        // Assert
        Assert.Equal("The customer is angry.", question.Instructions);
        Assert.Equal("The customer is angry.", question.TrueDescription);
        Assert.Null(question.FalseDescription);
    }

    private static JevDecisionClient CreateClient(HttpClient httpClient)
    {
        var options = new JevChatClientOptions
        {
            Transport = new HttpClientPipelineTransport(httpClient),
            RetryPolicy = new JevRetryPolicy { RecordedWaitsForTests = [] },
        };

        return new JevDecisionClient(new JevHttpClient(new ApiKeyCredential("test-key"), options, endpoint: null, modelId: "jev-test"));
    }
}
