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
    /// Converts a single <see cref="ChatMessage"/> to one or more Foundry evaluator message dicts.
    /// </summary>
    /// <remarks>
    /// A single message with multiple <see cref="FunctionResultContent"/> entries produces
    /// multiple output messages (one per tool result), matching the Foundry evaluator schema.
    /// </remarks>
    internal static List<Dictionary<string, object>> ConvertMessage(ChatMessage message)
    {
        var role = message.Role.Value;
        var contentItems = new List<Dictionary<string, object>>();
        var toolResults = new List<Dictionary<string, object>>();

        foreach (var content in message.Contents)
        {
            switch (content)
            {
                case TextContent tc when !string.IsNullOrEmpty(tc.Text):
                    contentItems.Add(new Dictionary<string, object>
                    {
                        ["type"] = "text",
                        ["text"] = tc.Text,
                    });
                    break;

                case UriContent uc when uc.HasTopLevelMediaType("image"):
                    contentItems.Add(new Dictionary<string, object>
                    {
                        ["type"] = "input_image",
                        ["image_url"] = uc.Uri.ToString(),
                        ["detail"] = "auto",
                    });
                    break;

                case DataContent dc when dc.HasTopLevelMediaType("image"):
                    contentItems.Add(new Dictionary<string, object>
                    {
                        ["type"] = "input_image",
                        ["image_url"] = dc.Uri,
                        ["detail"] = "auto",
                    });
                    break;

                case FunctionCallContent fc:
                    var tc2 = new Dictionary<string, object>
                    {
                        ["type"] = "tool_call",
                        ["tool_call_id"] = fc.CallId ?? string.Empty,
                        ["name"] = fc.Name ?? string.Empty,
                    };
                    if (fc.Arguments is { Count: > 0 })
                    {
                        tc2["arguments"] = fc.Arguments;
                    }

                    contentItems.Add(tc2);
                    break;

                case FunctionResultContent fr:
                    toolResults.Add(new Dictionary<string, object>
                    {
                        ["call_id"] = fr.CallId ?? string.Empty,
                        ["result"] = fr.Result ?? string.Empty,
                    });
                    break;
            }
        }

        var output = new List<Dictionary<string, object>>();

        if (toolResults.Count > 0)
        {
            foreach (var tr in toolResults)
            {
                output.Add(new Dictionary<string, object>
                {
                    ["role"] = "tool",
                    ["tool_call_id"] = tr["call_id"],
                    ["content"] = new List<Dictionary<string, object>>
                    {
                        new()
                        {
                            ["type"] = "tool_result",
                            ["tool_result"] = tr["result"],
                        },
                    },
                });
            }
        }
        else if (contentItems.Count > 0)
        {
            output.Add(new Dictionary<string, object>
            {
                ["role"] = role,
                ["content"] = contentItems,
            });
        }
        else
        {
            output.Add(new Dictionary<string, object>
            {
                ["role"] = role,
                ["content"] = new List<Dictionary<string, object>>
                {
                    new() { ["type"] = "text", ["text"] = string.Empty },
                },
            });
        }

        return output;
    }

    /// <summary>
    /// Converts a sequence of <see cref="ChatMessage"/> objects to Foundry evaluator format.
    /// </summary>
    internal static List<Dictionary<string, object>> ConvertMessages(IEnumerable<ChatMessage> messages)
    {
        var result = new List<Dictionary<string, object>>();
        foreach (var msg in messages)
        {
            result.AddRange(ConvertMessage(msg));
        }

        return result;
    }

    /// <summary>
    /// Converts an <see cref="EvalItem"/> to a JSONL dictionary for the Foundry Evals API.
    /// </summary>
    /// <remarks>
    /// Produces both string fields (query, response) for quality evaluators and
    /// conversation arrays (query_messages, response_messages) for agent evaluators.
    /// </remarks>
    internal static Dictionary<string, object> ConvertEvalItem(EvalItem item, IConversationSplitter? defaultSplitter = null)
    {
        var splitter = item.Splitter ?? defaultSplitter ?? ConversationSplitters.LastTurn;
        var (queryMessages, responseMessages) = splitter.Split(item.Conversation);

        var dict = new Dictionary<string, object>
        {
            ["query"] = item.Query,
            ["response"] = item.Response,
            ["query_messages"] = ConvertMessages(queryMessages),
            ["response_messages"] = ConvertMessages(responseMessages),
        };

        if (item.Context is not null)
        {
            dict["context"] = item.Context;
        }

        if (item.Tools is { Count: > 0 })
        {
            dict["tool_definitions"] = item.Tools
                .OfType<AIFunction>()
                .Select(t => new Dictionary<string, object?>
                {
                    ["name"] = t.Name,
                    ["description"] = t.Description,
                    ["parameters"] = t.JsonSchema,
                })
                .ToList();
        }

        return dict;
    }

    /// <summary>
    /// Builds the <c>testing_criteria</c> array for <c>evals.create()</c>.
    /// </summary>
    /// <param name="evaluators">Evaluator names (short or fully-qualified).</param>
    /// <param name="model">Model deployment name for the LLM judge.</param>
    /// <param name="includeDataMapping">
    /// Whether to include field-level data mapping (required for JSONL data source).
    /// </param>
    internal static List<Dictionary<string, object>> BuildTestingCriteria(
        IEnumerable<string> evaluators,
        string model,
        bool includeDataMapping = false)
    {
        var criteria = new List<Dictionary<string, object>>();
        foreach (var name in evaluators)
        {
            var qualified = ResolveEvaluator(name);
            var shortName = name.StartsWith("builtin.", StringComparison.Ordinal)
                ? name.Substring("builtin.".Length)
                : name;

            var entry = new Dictionary<string, object>
            {
                ["type"] = "azure_ai_evaluator",
                ["name"] = shortName,
                ["evaluator_name"] = qualified,
                ["initialization_parameters"] = new Dictionary<string, string>
                {
                    ["deployment_name"] = model,
                },
            };

            if (includeDataMapping)
            {
                var mapping = new Dictionary<string, string>();
                if (AgentEvaluators.Contains(qualified))
                {
                    mapping["query"] = "{{item.query_messages}}";
                    mapping["response"] = "{{item.response_messages}}";
                }
                else
                {
                    mapping["query"] = "{{item.query}}";
                    mapping["response"] = "{{item.response}}";
                }

                if (qualified == "builtin.groundedness")
                {
                    mapping["context"] = "{{item.context}}";
                }

                if (ToolEvaluators.Contains(qualified))
                {
                    mapping["tool_definitions"] = "{{item.tool_definitions}}";
                }

                entry["data_mapping"] = mapping;
            }

            criteria.Add(entry);
        }

        return criteria;
    }

    /// <summary>
    /// Builds the <c>item_schema</c> for custom JSONL eval definitions.
    /// </summary>
    internal static Dictionary<string, object> BuildItemSchema(bool hasContext = false, bool hasTools = false)
    {
        var properties = new Dictionary<string, object>
        {
            ["query"] = new Dictionary<string, string> { ["type"] = "string" },
            ["response"] = new Dictionary<string, string> { ["type"] = "string" },
            ["query_messages"] = new Dictionary<string, string> { ["type"] = "array" },
            ["response_messages"] = new Dictionary<string, string> { ["type"] = "array" },
        };

        if (hasContext)
        {
            properties["context"] = new Dictionary<string, string> { ["type"] = "string" };
        }

        if (hasTools)
        {
            properties["tool_definitions"] = new Dictionary<string, string> { ["type"] = "array" };
        }

        return new Dictionary<string, object>
        {
            ["type"] = "object",
            ["properties"] = properties,
            ["required"] = new List<string> { "query", "response" },
        };
    }

    /// <summary>
    /// Resolves a short evaluator name to its fully-qualified <c>builtin.*</c> form.
    /// </summary>
    internal static string ResolveEvaluator(string name)
    {
        if (name.StartsWith("builtin.", StringComparison.Ordinal))
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
    internal static readonly HashSet<string> AgentEvaluators = new(StringComparer.Ordinal)
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
    internal static readonly HashSet<string> ToolEvaluators = new(StringComparer.Ordinal)
    {
        "builtin.tool_call_accuracy",
        "builtin.tool_selection",
        "builtin.tool_input_accuracy",
        "builtin.tool_output_utilization",
        "builtin.tool_call_success",
    };

    // Short name → fully-qualified name mapping.
    internal static readonly Dictionary<string, string> BuiltinEvaluators = new(StringComparer.Ordinal)
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
