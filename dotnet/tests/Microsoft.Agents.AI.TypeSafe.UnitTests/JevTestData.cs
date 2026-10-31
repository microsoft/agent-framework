// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Text.Json;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.TypeSafe.UnitTests;

/// <summary>
/// A support-ticket request and response taken from the TypeSafe quick start, used across the tests.
/// </summary>
internal static class JevTestData
{
    public const string TicketText = "Hi, I've been trying to connect my Stripe account for 3 days and the integration keeps failing. I'm losing sales. Please help ASAP.";

    /// <summary>The tool arguments a model would write for the ticket, with the three question kinds.</summary>
    public const string RequestJson = """
        {
          "state": "Hi, I've been trying to connect my Stripe account for 3 days and the integration keeps failing. I'm losing sales. Please help ASAP.",
          "questions": {
            "department": {
              "type": "choice",
              "instructions": "Which team should handle this",
              "criteria": { "billing": "Payment or subscription issues", "technical": "Bugs or integration problems", "sales": null }
            },
            "frustration": {
              "type": "score",
              "instructions": "How frustrated the customer appears",
              "criteria": ["Calm, just stating facts", "Frustrated but civil", "Very angry, strong language"]
            },
            "is_urgent": {
              "type": "noul",
              "instructions": "The message conveys urgency or time-sensitivity",
              "criteria": { "true": "Explicitly time-sensitive", "false": "No urgency expressed" }
            }
          }
        }
        """;

    /// <summary>The API response for <see cref="RequestJson"/>.</summary>
    public const string ResponseJson = """
        {
          "model": "jev-1.13.0",
          "answers": {
            "department": { "type": "choice", "choice": "technical", "confidence": 0.78, "probabilities": { "technical": 0.85, "sales": 0.0, "billing": 0.15 } },
            "frustration": {
              "type": "score", "score": 1.0, "confidence": 1.0,
              "legend": { "0": "Calm, just stating facts", "1": "Frustrated but civil", "2": "Very angry, strong language" },
              "probabilities": { "0": 0.0, "1": 1.0, "2": 0.0 }
            },
            "is_urgent": { "type": "noul", "noul": 0.97 }
          },
          "usage": { "input_tokens": 392, "output_tokens": 65 }
        }
        """;

    /// <summary>Parses tool arguments the way chat clients do: one <see cref="JsonElement"/> per top-level property.</summary>
    public static AIFunctionArguments Arguments(string json)
    {
        var arguments = new AIFunctionArguments();
        using JsonDocument document = JsonDocument.Parse(json);
        foreach (JsonProperty property in document.RootElement.EnumerateObject())
        {
            arguments[property.Name] = property.Value.Clone();
        }

        return arguments;
    }

    /// <summary>Parses tool arguments into the dictionary shape that <see cref="FunctionCallContent"/> carries.</summary>
    public static Dictionary<string, object?> CallArguments(string json)
    {
        var arguments = new Dictionary<string, object?>();
        foreach (KeyValuePair<string, object?> argument in Arguments(json))
        {
            arguments[argument.Key] = argument.Value;
        }

        return arguments;
    }

    /// <summary>A correct result for <see cref="RequestJson"/>, built from the contract types.</summary>
    public static JevResult CreateResult() => new()
    {
        Model = "custom-model",
        Answers = new Dictionary<string, JevResponse>
        {
            ["department"] = new JevChoiceResponse
            {
                Choice = "technical",
                Confidence = 0.78,
                Probabilities = new Dictionary<string, double> { ["technical"] = 0.85, ["billing"] = 0.15, ["sales"] = 0 },
            },
            ["frustration"] = new JevScoreResponse
            {
                Score = 1,
                Confidence = 1,
                Legend = new Dictionary<string, JevEntry> { ["0"] = "Calm", ["1"] = "Frustrated", ["2"] = "Very angry" },
                Probabilities = new Dictionary<string, double> { ["0"] = 0, ["1"] = 1, ["2"] = 0 },
            },
            ["is_urgent"] = new JevNoulResponse { Noul = 0.97 },
        },
        Usage = new JevUsage { InputTokens = 10, OutputTokens = 5 },
    };
}
