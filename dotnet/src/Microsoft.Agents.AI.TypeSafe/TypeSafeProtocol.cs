// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Text;
using System.Text.Json;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.TypeSafe;

/// <summary>
/// The System One wire shape in one place: request serialization, provider-limit validation, response parsing, and
/// failure classification. Internal so the tests can pin the protocol without a network.
/// </summary>
internal static class TypeSafeProtocol
{
    /// <summary>The most choices a System One choice question accepts. A provider limit, not a contract one.</summary>
    internal const int MaxChoices = 255;

    /// <summary>The most levels a System One score question accepts. A provider limit, not a contract one.</summary>
    internal const int MaxScoreLevels = 10;

    private const int BodyExcerptLength = 500;

    internal static string SerializeRequest(DecisionRequest request, string modelId)
    {
        ValidateQuestions(request);

        using var stream = new MemoryStream();
        using (var writer = new Utf8JsonWriter(stream))
        {
            writer.WriteStartObject();
            writer.WriteString("model", modelId);

            writer.WritePropertyName("state");
            if (request.State.ValueKind == JsonValueKind.Undefined)
            {
                writer.WriteNullValue();
            }
            else
            {
                request.State.WriteTo(writer);
            }

            writer.WritePropertyName("questions");
            writer.WriteStartObject();
            foreach (DecisionQuestion question in request.Questions)
            {
                writer.WritePropertyName(question.Id);
                WriteQuestion(writer, question);
            }

            writer.WriteEndObject();
            writer.WriteEndObject();
        }

        return Encoding.UTF8.GetString(stream.ToArray());
    }

    private static void ValidateQuestions(DecisionRequest request)
    {
        if (request.Questions.Count == 0)
        {
            throw new DecisionClientException(DecisionFailureKind.InvalidRequest, "A decision request needs at least one question.");
        }

        var ids = new HashSet<string>(StringComparer.Ordinal);
        foreach (DecisionQuestion question in request.Questions)
        {
            if (question is null)
            {
                throw new DecisionClientException(DecisionFailureKind.InvalidRequest, "A decision request contains a null question.");
            }

            if (string.IsNullOrWhiteSpace(question.Id))
            {
                throw new DecisionClientException(DecisionFailureKind.InvalidRequest, "Question identifiers must not be empty.");
            }

            if (!ids.Add(question.Id))
            {
                throw new DecisionClientException(DecisionFailureKind.InvalidRequest, $"Question identifiers must be unique within a request; '{question.Id}' appears more than once.");
            }

            if (string.IsNullOrWhiteSpace(question.Instructions))
            {
                throw new DecisionClientException(DecisionFailureKind.InvalidRequest, $"Question '{question.Id}' has no instructions.");
            }
        }
    }

    private static void WriteQuestion(Utf8JsonWriter writer, DecisionQuestion question)
    {
        writer.WriteStartObject();
        switch (question)
        {
            case BinaryDecisionQuestion binary:
                writer.WriteString("type", "noul");
                writer.WriteString("instructions", binary.Instructions);
                if (binary.Criteria is { } criteria && (criteria.TrueDescription is not null || criteria.FalseDescription is not null))
                {
                    writer.WritePropertyName("criteria");
                    writer.WriteStartObject();
                    if (criteria.TrueDescription is not null)
                    {
                        writer.WriteString("true", criteria.TrueDescription);
                    }

                    if (criteria.FalseDescription is not null)
                    {
                        writer.WriteString("false", criteria.FalseDescription);
                    }

                    writer.WriteEndObject();
                }

                break;

            case ChoiceDecisionQuestion choice:
                if (choice.Choices.Count > MaxChoices)
                {
                    throw new DecisionClientException(DecisionFailureKind.InvalidRequest, $"A System One choice question accepts at most {MaxChoices} choices; question '{choice.Id}' has {choice.Choices.Count}.");
                }

                writer.WriteString("type", "choice");
                writer.WriteString("instructions", choice.Instructions);
                writer.WritePropertyName("criteria");
                writer.WriteStartObject();
                foreach (DecisionChoice option in choice.Choices)
                {
                    writer.WriteString(option.Name, option.Description ?? option.Name);
                }

                writer.WriteEndObject();
                break;

            case ScoreDecisionQuestion score:
                if (score.Levels.Count > MaxScoreLevels)
                {
                    throw new DecisionClientException(DecisionFailureKind.InvalidRequest, $"A System One score question accepts at most {MaxScoreLevels} levels; question '{score.Id}' has {score.Levels.Count}.");
                }

                writer.WriteString("type", "score");
                writer.WriteString("instructions", score.Instructions);
                writer.WritePropertyName("criteria");
                writer.WriteStartArray();
                foreach (DecisionScoreLevel level in score.Levels)
                {
                    writer.WriteStringValue(level.Description);
                }

                writer.WriteEndArray();
                break;

            default:
                throw new DecisionClientException(DecisionFailureKind.InvalidRequest, $"Question '{question.Id}' is of an unsupported kind ({question.GetType().Name}).");
        }

        writer.WriteEndObject();
    }

    internal static DecisionClientException ClassifyFailure(int statusCode, string body, string host)
    {
        DecisionFailureKind kind = statusCode switch
        {
            401 or 403 => DecisionFailureKind.Authentication,
            400 or 422 => DecisionFailureKind.InvalidRequest,
            429 => DecisionFailureKind.RateLimited,
            529 => DecisionFailureKind.Overloaded,
            >= 500 and <= 599 => DecisionFailureKind.ProviderUnavailable,
            _ => DecisionFailureKind.Unknown,
        };

        return new DecisionClientException(kind, $"{host} answered HTTP {statusCode} ({kind}): {Excerpt(body)}", statusCode);
    }

    internal static DecisionResponse ParseResponse(string body, DecisionRequest request, string host)
    {
        JsonDocument document;
        try
        {
            document = JsonDocument.Parse(body);
        }
        catch (JsonException ex)
        {
            throw Invalid($"{host} answered with a body that is not JSON: {Excerpt(body)}", ex);
        }

        using (document)
        {
            JsonElement root = document.RootElement;
            if (root.ValueKind != JsonValueKind.Object)
            {
                throw Invalid($"{host} answered with a JSON {root.ValueKind}, not an object.");
            }

            if (!root.TryGetProperty("model", out JsonElement modelElement) || modelElement.ValueKind != JsonValueKind.String || string.IsNullOrWhiteSpace(modelElement.GetString()))
            {
                throw Invalid($"{host} answered without a 'model' field naming what answered.");
            }

            if (!root.TryGetProperty("answers", out JsonElement answersElement) || answersElement.ValueKind != JsonValueKind.Object)
            {
                throw Invalid($"{host} answered without an 'answers' object.");
            }

            var answers = new Dictionary<string, DecisionAnswer>(StringComparer.Ordinal);
            foreach (DecisionQuestion question in request.Questions)
            {
                if (!answersElement.TryGetProperty(question.Id, out JsonElement answerElement) || answerElement.ValueKind != JsonValueKind.Object)
                {
                    throw Invalid($"{host} returned no answer for question '{question.Id}'.");
                }

                answers[question.Id] = ParseAnswer(question, answerElement, host);
            }

            var response = new DecisionResponse(answers)
            {
                ModelId = modelElement.GetString(),
                RawRepresentation = root.Clone(),
            };

            if (root.TryGetProperty("id", out JsonElement idElement) && idElement.ValueKind == JsonValueKind.String)
            {
                response.ResponseId = idElement.GetString();
            }

            if (root.TryGetProperty("usage", out JsonElement usageElement) && usageElement.ValueKind == JsonValueKind.Object)
            {
                long input = ReadLong(usageElement, "input_tokens", host);
                long output = ReadLong(usageElement, "output_tokens", host);
                response.Usage = new UsageDetails
                {
                    InputTokenCount = input,
                    OutputTokenCount = output,
                    TotalTokenCount = input + output,
                };

                // OpenRouter's relay reports the billed cost; TypeSafe does not. Surface it without pretending it is a token count.
                if (usageElement.TryGetProperty("cost", out JsonElement costElement) && costElement.ValueKind == JsonValueKind.Number)
                {
                    response.AdditionalProperties ??= [];
                    response.AdditionalProperties["cost"] = costElement.GetDouble();
                }
            }

            return response;
        }
    }

    private static DecisionAnswer ParseAnswer(DecisionQuestion question, JsonElement element, string host)
    {
        string expected = question switch
        {
            BinaryDecisionQuestion => "noul",
            ChoiceDecisionQuestion => "choice",
            ScoreDecisionQuestion => "score",
            _ => throw Invalid($"Question '{question.Id}' is of an unsupported kind ({question.GetType().Name})."),
        };

        if (!element.TryGetProperty("type", out JsonElement typeElement) || typeElement.ValueKind != JsonValueKind.String)
        {
            throw Invalid($"{host}: answer '{question.Id}' has no 'type'.");
        }

        string? type = typeElement.GetString();
        if (!string.Equals(type, expected, StringComparison.Ordinal))
        {
            throw Invalid($"{host}: answer '{question.Id}' is a '{type}' answer to a '{expected}' question.");
        }

        try
        {
            switch (question)
            {
                case BinaryDecisionQuestion:
                    return new BinaryDecisionAnswer(ReadDouble(element, "noul", question.Id, host)) { RawRepresentation = element.Clone() };

                case ChoiceDecisionQuestion choiceQuestion:
                {
                    string selected = ReadString(element, "choice", question.Id, host);
                    Dictionary<string, double> probabilities = ReadDistribution(element, question.Id, host);

                    foreach (DecisionChoice option in choiceQuestion.Choices)
                    {
                        if (!probabilities.ContainsKey(option.Name))
                        {
                            throw Invalid($"{host}: answer '{question.Id}' has no probability for choice '{option.Name}'.");
                        }
                    }

                    if (!probabilities.ContainsKey(selected))
                    {
                        throw Invalid($"{host}: answer '{question.Id}' selected '{selected}', which is not one of the requested choices.");
                    }

                    return new ChoiceDecisionAnswer(selected, probabilities)
                    {
                        Confidence = ReadOptionalDouble(element, "confidence", question.Id, host),
                        RawRepresentation = element.Clone(),
                    };
                }

                case ScoreDecisionQuestion scoreQuestion:
                {
                    var probabilities = new Dictionary<int, double>();
                    foreach (KeyValuePair<string, double> pair in ReadDistribution(element, question.Id, host))
                    {
                        // Levels are 0-indexed on the wire: "0" is the first level supplied.
                        if (!int.TryParse(pair.Key, NumberStyles.Integer, CultureInfo.InvariantCulture, out int index) || index < 0 || index >= scoreQuestion.Levels.Count)
                        {
                            throw Invalid($"{host}: answer '{question.Id}' has a probability for unknown level '{pair.Key}'.");
                        }

                        probabilities[index] = pair.Value;
                    }

                    for (int i = 0; i < scoreQuestion.Levels.Count; i++)
                    {
                        if (!probabilities.ContainsKey(i))
                        {
                            throw Invalid($"{host}: answer '{question.Id}' has no probability for level {i}.");
                        }
                    }

                    var answer = new ScoreDecisionAnswer(ReadDouble(element, "score", question.Id, host), probabilities)
                    {
                        Confidence = ReadOptionalDouble(element, "confidence", question.Id, host),
                        RawRepresentation = element.Clone(),
                    };

                    if (element.TryGetProperty("legend", out JsonElement legend) && legend.ValueKind == JsonValueKind.Object)
                    {
                        answer.AdditionalProperties = new AdditionalPropertiesDictionary { ["legend"] = legend.Clone() };
                    }

                    return answer;
                }

                default:
                    throw Invalid($"Question '{question.Id}' is of an unsupported kind ({question.GetType().Name}).");
            }
        }
        catch (ArgumentException ex)
        {
            // The answer types validate their own ranges (probability outside 0..1, blank choice).
            throw Invalid($"{host}: answer '{question.Id}' is out of range: {ex.Message}", ex);
        }
    }

    private static double ReadDouble(JsonElement element, string name, string id, string host)
    {
        if (!element.TryGetProperty(name, out JsonElement value) || value.ValueKind != JsonValueKind.Number)
        {
            throw Invalid($"{host}: answer '{id}' has no numeric '{name}'.");
        }

        return value.GetDouble();
    }

    private static double? ReadOptionalDouble(JsonElement element, string name, string id, string host)
    {
        if (!element.TryGetProperty(name, out JsonElement value) || value.ValueKind == JsonValueKind.Null)
        {
            return null;
        }

        if (value.ValueKind != JsonValueKind.Number)
        {
            throw Invalid($"{host}: answer '{id}' has a non-numeric '{name}'.");
        }

        return value.GetDouble();
    }

    private static long ReadLong(JsonElement element, string name, string host)
    {
        if (!element.TryGetProperty(name, out JsonElement value) || value.ValueKind != JsonValueKind.Number)
        {
            throw Invalid($"{host}: usage has no numeric '{name}'.");
        }

        return value.TryGetInt64(out long result) ? result : (long)value.GetDouble();
    }

    private static string ReadString(JsonElement element, string name, string id, string host)
    {
        if (!element.TryGetProperty(name, out JsonElement value) || value.ValueKind != JsonValueKind.String)
        {
            throw Invalid($"{host}: answer '{id}' has no string '{name}'.");
        }

        return value.GetString()!;
    }

    private static Dictionary<string, double> ReadDistribution(JsonElement element, string id, string host)
    {
        if (!element.TryGetProperty("probabilities", out JsonElement value) || value.ValueKind != JsonValueKind.Object)
        {
            throw Invalid($"{host}: answer '{id}' has no 'probabilities' object.");
        }

        var map = new Dictionary<string, double>(StringComparer.Ordinal);
        foreach (JsonProperty property in value.EnumerateObject())
        {
            if (property.Value.ValueKind != JsonValueKind.Number)
            {
                throw Invalid($"{host}: answer '{id}' has a non-numeric probability for '{property.Name}'.");
            }

            double probability = property.Value.GetDouble();
            if (double.IsNaN(probability) || probability < 0 || probability > 1)
            {
                throw Invalid($"{host}: answer '{id}' has a probability outside 0..1 for '{property.Name}'.");
            }

            map[property.Name] = probability;
        }

        return map;
    }

    private static DecisionClientException Invalid(string message, Exception? inner = null) =>
        new(DecisionFailureKind.InvalidResponse, message, statusCode: null, innerException: inner);

    private static string Excerpt(string body)
    {
        if (string.IsNullOrWhiteSpace(body))
        {
            return "<empty body>";
        }

        string flat = body.Replace('\r', ' ').Replace('\n', ' ').Trim();
        return flat.Length <= BodyExcerptLength ? flat : string.Concat(flat.AsSpan(0, BodyExcerptLength), "…");
    }
}
