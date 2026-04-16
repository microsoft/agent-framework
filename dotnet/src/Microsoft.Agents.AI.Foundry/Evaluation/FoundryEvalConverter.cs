// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Foundry;

/// <summary>
/// Converts MEAI <see cref="ChatMessage"/> objects to the Foundry evaluator JSON format.
/// </summary>
/// <remarks>
/// Handles the type gap between MEAI's <see cref="ChatMessage"/> / <see cref="AIContent"/> types
/// and the OpenAI-style agent message schema used by Foundry evaluation providers.
/// </remarks>
internal static class FoundryEvalConverter
{
    /// <summary>
    /// Converts a single <see cref="ChatMessage"/> to one or more Foundry evaluator wire messages.
    /// </summary>
    /// <remarks>
    /// A single message with multiple <see cref="FunctionResultContent"/> entries produces
    /// multiple output messages (one per tool result), matching the Foundry evaluator schema.
    /// </remarks>
    internal static List<WireMessage> ConvertMessage(ChatMessage message)
    {
        var role = message.Role.Value;
        var contentItems = new List<WireContentItem>();
        var toolResults = new List<(string CallId, object Result)>();

        foreach (var content in message.Contents)
        {
            switch (content)
            {
                case TextContent tc when !string.IsNullOrEmpty(tc.Text):
                    contentItems.Add(new WireTextContent { Text = tc.Text });
                    break;

                case UriContent uc when uc.HasTopLevelMediaType("image"):
                    contentItems.Add(new WireImageContent { ImageUrl = uc.Uri.ToString() });
                    break;

                case DataContent dc when dc.HasTopLevelMediaType("image"):
                    contentItems.Add(new WireImageContent { ImageUrl = dc.Uri });
                    break;

                case FunctionCallContent fc:
                    contentItems.Add(new WireToolCallContent
                    {
                        ToolCallId = fc.CallId ?? string.Empty,
                        Name = fc.Name ?? string.Empty,
                        Arguments = fc.Arguments is { Count: > 0 } ? fc.Arguments : null,
                    });
                    break;

                case FunctionResultContent fr:
                    toolResults.Add((fr.CallId ?? string.Empty, fr.Result ?? string.Empty));
                    break;
            }
        }

        var output = new List<WireMessage>();

        if (toolResults.Count > 0)
        {
            // Tool results take precedence — the Foundry Evals API expects tool messages
            // to have role=tool with a single tool_result content. Any text content in the
            // same message is omitted since the API format doesn't support mixed content.
            foreach (var (callId, result) in toolResults)
            {
                output.Add(new WireMessage
                {
                    Role = "tool",
                    ToolCallId = callId,
                    Content = [new WireToolResultContent { ToolResult = result }],
                });
            }
        }
        else if (contentItems.Count > 0)
        {
            output.Add(new WireMessage
            {
                Role = role,
                Content = contentItems,
            });
        }
        else
        {
            output.Add(new WireMessage
            {
                Role = role,
                Content = [new WireTextContent { Text = string.Empty }],
            });
        }

        return output;
    }

    /// <summary>
    /// Converts a sequence of <see cref="ChatMessage"/> objects to Foundry evaluator format.
    /// </summary>
    internal static List<WireMessage> ConvertMessages(IEnumerable<ChatMessage> messages)
    {
        var result = new List<WireMessage>();
        foreach (var msg in messages)
        {
            result.AddRange(ConvertMessage(msg));
        }

        return result;
    }

    /// <summary>
    /// Converts an <see cref="EvalItem"/> to a wire-format payload for the Foundry Evals API.
    /// </summary>
    /// <remarks>
    /// Produces both string fields (query, response) for quality evaluators and
    /// conversation arrays (query_messages, response_messages) for agent evaluators.
    /// </remarks>
    internal static WireEvalItemPayload ConvertEvalItem(EvalItem item, IConversationSplitter? defaultSplitter = null)
    {
        var splitter = item.Splitter ?? defaultSplitter ?? ConversationSplitters.LastTurn;
        var (queryMessages, responseMessages) = splitter.Split(item.Conversation);

        return new WireEvalItemPayload
        {
            Query = item.Query,
            Response = item.Response,
            QueryMessages = ConvertMessages(queryMessages),
            ResponseMessages = ConvertMessages(responseMessages),
            Context = item.Context,
            ToolDefinitions = item.Tools is { Count: > 0 }
                ? item.Tools
                    .OfType<AIFunction>()
                    .Select(t => new WireToolDefinition
                    {
                        Name = t.Name,
                        Description = t.Description,
                        Parameters = t.JsonSchema,
                    })
                    .ToList()
                : null,
        };
    }

    /// <summary>
    /// Builds the <c>testing_criteria</c> array for <c>evals.create()</c>.
    /// </summary>
    /// <param name="evaluators">Evaluator names (short or fully-qualified).</param>
    /// <param name="model">Model deployment name for the LLM judge.</param>
    /// <param name="includeDataMapping">
    /// Whether to include field-level data mapping (required for JSONL data source).
    /// </param>
    internal static List<WireTestingCriterion> BuildTestingCriteria(
        IEnumerable<string> evaluators,
        string model,
        bool includeDataMapping = false)
    {
        var criteria = new List<WireTestingCriterion>();
        foreach (var name in evaluators)
        {
            var qualified = ResolveEvaluator(name);
            var shortName = name.StartsWith("builtin.", StringComparison.Ordinal)
                ? name.Substring("builtin.".Length)
                : name;

            Dictionary<string, string>? dataMapping = null;
            if (includeDataMapping)
            {
                dataMapping = new Dictionary<string, string>();
                if (AgentEvaluators.Contains(qualified))
                {
                    dataMapping["query"] = "{{item.query_messages}}";
                    dataMapping["response"] = "{{item.response_messages}}";
                }
                else
                {
                    dataMapping["query"] = "{{item.query}}";
                    dataMapping["response"] = "{{item.response}}";
                }

                if (qualified == "builtin.groundedness")
                {
                    dataMapping["context"] = "{{item.context}}";
                }

                if (ToolEvaluators.Contains(qualified))
                {
                    dataMapping["tool_definitions"] = "{{item.tool_definitions}}";
                }
            }

            criteria.Add(new WireTestingCriterion
            {
                Name = shortName,
                EvaluatorName = qualified,
                InitializationParameters = new WireInitParams { DeploymentName = model },
                DataMapping = dataMapping,
            });
        }

        return criteria;
    }

    /// <summary>
    /// Builds the <c>item_schema</c> for custom JSONL eval definitions.
    /// </summary>
    internal static WireItemSchema BuildItemSchema(bool hasContext = false, bool hasTools = false)
    {
        var properties = new Dictionary<string, WireSchemaProperty>
        {
            ["query"] = new() { Type = "string" },
            ["response"] = new() { Type = "string" },
            ["query_messages"] = new() { Type = "array" },
            ["response_messages"] = new() { Type = "array" },
        };

        if (hasContext)
        {
            properties["context"] = new WireSchemaProperty { Type = "string" };
        }

        if (hasTools)
        {
            properties["tool_definitions"] = new WireSchemaProperty { Type = "array" };
        }

        return new WireItemSchema
        {
            Properties = properties,
            Required = ["query", "response"],
        };
    }

    /// <summary>
    /// Resolves a short evaluator name to its fully-qualified <c>builtin.*</c> form.
    /// </summary>
    internal static string ResolveEvaluator(string name)
    {
        if (name.StartsWith("builtin.", StringComparison.OrdinalIgnoreCase))
        {
            return name;
        }

        if (BuiltinEvaluators.TryGetValue(name, out var qualified))
        {
            return qualified;
        }

        throw new ArgumentException(
            $"Unknown evaluator '{name}'. Available: {string.Join(", ", BuiltinEvaluators.Keys.Order())}",
            nameof(name));
    }

    // Agent evaluators that accept query/response as conversation arrays.
    internal static readonly HashSet<string> AgentEvaluators = new(StringComparer.OrdinalIgnoreCase)
    {
        "builtin.intent_resolution",
        "builtin.task_adherence",
        "builtin.task_completion",
        "builtin.task_navigation_efficiency",
        "builtin.tool_call_accuracy",
        "builtin.tool_selection",
        "builtin.tool_input_accuracy",
        "builtin.tool_output_utilization",
        "builtin.tool_call_success",
    };

    // Evaluators that additionally require tool_definitions.
    internal static readonly HashSet<string> ToolEvaluators = new(StringComparer.OrdinalIgnoreCase)
    {
        "builtin.tool_call_accuracy",
        "builtin.tool_selection",
        "builtin.tool_input_accuracy",
        "builtin.tool_output_utilization",
        "builtin.tool_call_success",
    };

    // Short name → fully-qualified name mapping.
    internal static readonly Dictionary<string, string> BuiltinEvaluators = new(StringComparer.OrdinalIgnoreCase)
    {
        // Agent behavior
        ["intent_resolution"] = "builtin.intent_resolution",
        ["task_adherence"] = "builtin.task_adherence",
        ["task_completion"] = "builtin.task_completion",
        ["task_navigation_efficiency"] = "builtin.task_navigation_efficiency",
        // Tool usage
        ["tool_call_accuracy"] = "builtin.tool_call_accuracy",
        ["tool_selection"] = "builtin.tool_selection",
        ["tool_input_accuracy"] = "builtin.tool_input_accuracy",
        ["tool_output_utilization"] = "builtin.tool_output_utilization",
        ["tool_call_success"] = "builtin.tool_call_success",
        // Quality
        ["coherence"] = "builtin.coherence",
        ["fluency"] = "builtin.fluency",
        ["relevance"] = "builtin.relevance",
        ["groundedness"] = "builtin.groundedness",
        ["response_completeness"] = "builtin.response_completeness",
        ["similarity"] = "builtin.similarity",
        // Safety
        ["violence"] = "builtin.violence",
        ["sexual"] = "builtin.sexual",
        ["self_harm"] = "builtin.self_harm",
        ["hate_unfairness"] = "builtin.hate_unfairness",
    };
}
