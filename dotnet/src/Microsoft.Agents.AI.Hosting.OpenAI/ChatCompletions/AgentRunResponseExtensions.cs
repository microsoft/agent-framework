// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json;
using Microsoft.Agents.AI.Hosting.OpenAI.ChatCompletions.Models;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Hosting.OpenAI.ChatCompletions;

/// <summary>
/// Extension methods for converting agent responses to ChatCompletion models.
/// </summary>
internal static class AgentRunResponseExtensions
{
    public static ChatCompletion ToChatCompletion(this AgentRunResponse agentRunResponse, CreateChatCompletion request)
    {
        IList<ChatCompletionChoice> choices = agentRunResponse.ToChoices();

        return new ChatCompletion
        {
            Id = IdGeneratorHelpers.NewId(prefix: "chatcmpl", delimiter: "-", stringLength: 13),
            Choices = choices,
            Created = (agentRunResponse.CreatedAt ?? DateTimeOffset.UtcNow).ToUnixTimeSeconds(),
            Model = /* request.Agent?.Name ?? */ request.Model,
            Usage = agentRunResponse.Usage.ToCompletionUsage(),
            ServiceTier = request.ServiceTier ?? "default"
        };
    }

    public static List<ChatCompletionChoice> ToChoices(this AgentRunResponse agentRunResponse)
    {
        var chatCompletionChoices = new List<ChatCompletionChoice>();
        var index = 0;

        var finishReason = (agentRunResponse.RawRepresentation is ChatResponse { FinishReason: not null } chatResponse)
            ? chatResponse.FinishReason.ToString()
            : "stop"; // "stop" is a natural stop point; returning this by-default

        foreach (var message in agentRunResponse.Messages)
        {
            foreach (var content in message.Contents)
            {
                ChoiceMessage choiceMessage = content switch
                {
                    // text
                    TextContent textContent => new()
                    {
                        Content = textContent.Text
                    },

                    // image, see how MessageContentPartConverter packs the content types
                    DataContent imageContent when imageContent.HasTopLevelMediaType("image") => new()
                    {
                        Content = imageContent.Base64Data.ToString()
                    },
                    UriContent urlContent when urlContent.HasTopLevelMediaType("image") => new()
                    {
                        Content = urlContent.Uri.ToString()
                    },

                    // audio
                    DataContent audioContent when audioContent.HasTopLevelMediaType("audio") => new()
                    {
                        Audio = new()
                        {
                            Data = audioContent.Base64Data.ToString(),
                            Id = audioContent.Name,
                            //Transcript = ,
                            //ExpiresAt = ,
                        },
                    },

                    // file (neither audio nor image)
                    DataContent fileContent => new()
                    {
                        Content = fileContent.Base64Data.ToString()
                    },
                    HostedFileContent fileContent => new()
                    {
                        Content = fileContent.FileId
                    },

                    // function
                    FunctionCallContent functionCallContent => new()
                    {
                        ToolCalls = [functionCallContent.ToChoiceMessageToolCall()]
                    },

                    _ => throw new InvalidOperationException($"Got unsupported content: {content.GetType()}")
                };

                choiceMessage.Role = message.Role.Value;
                choiceMessage.Annotations = content.Annotations?.ToChoiceMessageAnnotations();

                var choice = new ChatCompletionChoice
                {
                    Index = index++,
                    Message = choiceMessage,
                    FinishReason = finishReason
                };

                chatCompletionChoices.Add(choice);
            }
        }

        return chatCompletionChoices;
    }

    /// <summary>
    /// Converts UsageDetails to ResponseUsage.
    /// </summary>
    /// <param name="usage">The usage details to convert.</param>
    /// <returns>A ResponseUsage object with zeros if usage is null.</returns>
    public static CompletionUsage ToCompletionUsage(this UsageDetails? usage)
    {
        if (usage == null)
        {
            return CompletionUsage.Zero;
        }

        var cachedTokens = usage.AdditionalCounts?.TryGetValue("InputTokenDetails.CachedTokenCount", out var cachedInputToken) ?? false
            ? (int)cachedInputToken
            : 0;
        var reasoningTokens =
            usage.AdditionalCounts?.TryGetValue("OutputTokenDetails.ReasoningTokenCount", out var reasoningToken) ?? false
                ? (int)reasoningToken
                : 0;

        return new CompletionUsage
        {
            PromptTokens = (int)(usage.InputTokenCount ?? 0),
            PromptTokensDetails = new() { CachedTokens = cachedTokens },
            CompletionTokens = (int)(usage.OutputTokenCount ?? 0),
            CompletionTokensDetails = new() { ReasoningTokens = reasoningTokens },
            TotalTokens = (int)(usage.TotalTokenCount ?? 0)
        };
    }

    public static IList<ChoiceMessageAnnotation> ToChoiceMessageAnnotations(this IList<AIAnnotation> annotations)
    {
        var result = new List<ChoiceMessageAnnotation>();
        foreach (var annotation in annotations.OfType<CitationAnnotation>())
        {
            if (annotation is null)
            {
                continue;
            }

            // may point to mulitple regions in the AIContent.
            // we need to unroll another loop for regions then -> chatCompletions only point to single region per annotation

            var regions = annotation.AnnotatedRegions?.OfType<TextSpanAnnotatedRegion>().Where(x => x.StartIndex is not null && x.EndIndex is not null);
            if (regions is not null)
            {
                foreach (var region in regions)
                {
                    result.Add(new()
                    {
                        AnnotationUrlCitation = new AnnotationUrlCitation
                        {
                            Url = annotation.Url?.ToString(),
                            Title = annotation.Title,
                            StartIndex = region.StartIndex,
                            EndIndex = region.EndIndex
                        }
                    });
                }
            }
            else
            {
                result.Add(new()
                {
                    AnnotationUrlCitation = new AnnotationUrlCitation
                    {
                        Url = annotation.Url?.ToString(),
                        Title = annotation.Title
                    }
                });
            }
        }

        return result;
    }

    private static ChoiceMessageToolCall ToChoiceMessageToolCall(this FunctionCallContent functionCall)
    {
        return new()
        {
            Id = functionCall.CallId,
            Function = new()
            {
                Name = functionCall.Name,
                Arguments = JsonSerializer.Serialize(functionCall.Arguments, ChatCompletionsJsonContext.Default.DictionaryStringObject)
            }
        };
    }
}
