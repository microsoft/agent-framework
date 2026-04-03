// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI;

/// <summary>
/// Specifies how <see cref="EvalChecks.ToolCalledCheck(ToolCalledMode, string[])"/> matches tool names.
/// </summary>
public enum ToolCalledMode
{
    /// <summary>All specified tools must have been called.</summary>
    All,

    /// <summary>At least one of the specified tools must have been called.</summary>
    Any,
}

/// <summary>
/// Built-in check functions for common evaluation patterns.
/// </summary>
public static class EvalChecks
{
    /// <summary>
    /// Creates a check that verifies the response contains all specified keywords.
    /// </summary>
    /// <param name="keywords">Keywords that must appear in the response.</param>
    /// <returns>An <see cref="EvalCheck"/> delegate.</returns>
    public static EvalCheck KeywordCheck(params string[] keywords)
    {
        return KeywordCheck(caseSensitive: false, keywords);
    }

    /// <summary>
    /// Creates a check that verifies the response contains all specified keywords.
    /// </summary>
    /// <param name="caseSensitive">Whether the comparison is case-sensitive.</param>
    /// <param name="keywords">Keywords that must appear in the response.</param>
    /// <returns>An <see cref="EvalCheck"/> delegate.</returns>
    public static EvalCheck KeywordCheck(bool caseSensitive, params string[] keywords)
    {
        return (EvalItem item) =>
        {
            var comparison = caseSensitive
                ? StringComparison.Ordinal
                : StringComparison.OrdinalIgnoreCase;

            var missing = keywords
                .Where(kw => !item.Response.Contains(kw, comparison))
                .ToList();

            var passed = missing.Count == 0;
            var reason = passed
                ? $"All keywords found: {string.Join(", ", keywords)}"
                : $"Missing keywords: {string.Join(", ", missing)}";

            return new EvalCheckResult(passed, reason, "keyword_check");
        };
    }

    /// <summary>
    /// Creates a check that verifies specific tools were called in the conversation.
    /// All specified tools must have been called.
    /// </summary>
    /// <param name="toolNames">Tool names that must appear in the conversation.</param>
    /// <returns>An <see cref="EvalCheck"/> delegate.</returns>
    public static EvalCheck ToolCalledCheck(params string[] toolNames)
    {
        return ToolCalledCheck(ToolCalledMode.All, toolNames);
    }

    /// <summary>
    /// Creates a check that verifies specific tools were called in the conversation.
    /// </summary>
    /// <param name="mode">Whether <see cref="ToolCalledMode.All"/> or <see cref="ToolCalledMode.Any"/> of the specified tools must be called.</param>
    /// <param name="toolNames">Tool names to check for.</param>
    /// <returns>An <see cref="EvalCheck"/> delegate.</returns>
    public static EvalCheck ToolCalledCheck(ToolCalledMode mode, params string[] toolNames)
    {
        return (EvalItem item) =>
        {
            var calledTools = GetCalledTools(item);

            if (mode == ToolCalledMode.Any)
            {
                var found = toolNames.Where(t => calledTools.Contains(t)).ToList();
                var passed = found.Count > 0;
                var reason = passed
                    ? $"Called: {string.Join(", ", found)}"
                    : $"None of expected tools called: {string.Join(", ", toolNames)}";
                return new EvalCheckResult(passed, reason, "tool_called_check");
            }

            var missing = toolNames.Where(t => !calledTools.Contains(t)).ToList();
            var allPassed = missing.Count == 0;
            var allReason = allPassed
                ? $"All tools called: {string.Join(", ", toolNames)}"
                : $"Missing tool calls: {string.Join(", ", missing)}";

            return new EvalCheckResult(allPassed, allReason, "tool_called_check");
        };
    }

    /// <summary>
    /// A check that verifies at least one tool was called in the conversation.
    /// </summary>
    /// <returns>An <see cref="EvalCheck"/> delegate.</returns>
    public static EvalCheck ToolCallsPresent()
    {
        return (EvalItem item) =>
        {
            var calledTools = GetCalledTools(item);
            var passed = calledTools.Count > 0;
            var reason = passed
                ? $"Tools called: {string.Join(", ", calledTools)}"
                : "No tool calls found in conversation";

            return new EvalCheckResult(passed, reason, "tool_calls_present");
        };
    }

    /// <summary>
    /// A check that verifies expected tool calls match on name and optionally arguments.
    /// </summary>
    /// <remarks>
    /// <para>
    /// For each expected tool call, finds matching calls in the conversation by name.
    /// If <see cref="ExpectedToolCall.Arguments"/> is provided, checks that the actual
    /// arguments contain all expected key-value pairs (subset match — extra actual arguments are OK).
    /// </para>
    /// <para>If no expected tool calls are set on the item, the check passes.</para>
    /// </remarks>
    /// <returns>An <see cref="EvalCheck"/> delegate.</returns>
    public static EvalCheck ToolCallArgsMatch()
    {
        return (EvalItem item) =>
        {
            var expected = item.ExpectedToolCalls;
            if (expected is null || expected.Count == 0)
            {
                return new EvalCheckResult(true, "No expected tool calls specified.", "tool_call_args_match");
            }

            var actualCalls = GetCalledToolsWithArgs(item);
            int matched = 0;
            var details = new List<string>();

            foreach (var exp in expected)
            {
                var matching = actualCalls.Where(c => string.Equals(c.Name, exp.Name, StringComparison.OrdinalIgnoreCase)).ToList();

                if (matching.Count == 0)
                {
                    details.Add($"  {exp.Name}: not called");
                    continue;
                }

                if (exp.Arguments is null)
                {
                    matched++;
                    details.Add($"  {exp.Name}: called (args not checked)");
                    continue;
                }

                // Subset match — all expected keys present with expected values
                bool found = false;
                foreach (var call in matching)
                {
                    if (call.Arguments is not null
                        && exp.Arguments.All(kvp =>
                            call.Arguments.TryGetValue(kvp.Key, out var actual)
                            && Equals(actual, kvp.Value)))
                    {
                        found = true;
                        break;
                    }
                }

                if (found)
                {
                    matched++;
                    details.Add($"  {exp.Name}: args match");
                }
                else
                {
                    details.Add($"  {exp.Name}: args mismatch");
                }
            }

            var passed = matched == expected.Count;
            var reason = $"Tool call args match: {matched}/{expected.Count}\n{string.Join("\n", details)}";
            return new EvalCheckResult(passed, reason, "tool_call_args_match");
        };
    }

    /// <summary>
    /// Creates a check that verifies the response is non-empty and meets a minimum length.
    /// </summary>
    /// <param name="minLength">Minimum response length (default 1).</param>
    /// <returns>An <see cref="EvalCheck"/> delegate.</returns>
    public static EvalCheck NonEmpty(int minLength = 1)
    {
        return (EvalItem item) =>
        {
            var trimmed = item.Response.Trim();
            var passed = trimmed.Length >= minLength;
            var reason = passed
                ? $"Response length {trimmed.Length} meets minimum {minLength}"
                : $"Response length {trimmed.Length} is below minimum {minLength}";

            return new EvalCheckResult(passed, reason, "non_empty");
        };
    }

    /// <summary>
    /// Creates a check that verifies the response contains the expected output text.
    /// </summary>
    /// <param name="caseSensitive">Whether the comparison is case-sensitive (default false).</param>
    /// <returns>An <see cref="EvalCheck"/> delegate.</returns>
    public static EvalCheck ContainsExpected(bool caseSensitive = false)
    {
        return (EvalItem item) =>
        {
            if (string.IsNullOrEmpty(item.ExpectedOutput))
            {
                return new EvalCheckResult(false, "ExpectedOutput is not set; check cannot be applied.", "contains_expected");
            }

            var comparison = caseSensitive
                ? StringComparison.Ordinal
                : StringComparison.OrdinalIgnoreCase;

            var passed = item.Response.Contains(item.ExpectedOutput, comparison);
            var reason = passed
                ? $"Response contains expected output: \"{item.ExpectedOutput}\""
                : $"Response does not contain expected output: \"{item.ExpectedOutput}\"";

            return new EvalCheckResult(passed, reason, "contains_expected");
        };
    }

    /// <summary>
    /// A check that verifies the conversation contains at least one image
    /// (<see cref="DataContent"/> or <see cref="UriContent"/> with an image media type).
    /// </summary>
    /// <returns>An <see cref="EvalCheck"/> delegate.</returns>
    public static EvalCheck HasImageContent()
    {
        return (EvalItem item) =>
        {
            var passed = item.HasImageContent;
            var reason = passed
                ? "Conversation contains image content"
                : "No image content found in conversation";

            return new EvalCheckResult(passed, reason, "has_image_content");
        };
    }

    private static HashSet<string> GetCalledTools(EvalItem item)
    {
        var calledTools = new HashSet<string>(StringComparer.OrdinalIgnoreCase);

        foreach (var message in item.Conversation)
        {
            foreach (var content in message.Contents)
            {
                if (content is FunctionCallContent functionCall)
                {
                    calledTools.Add(functionCall.Name);
                }
            }
        }

        return calledTools;
    }

    private static List<(string Name, IReadOnlyDictionary<string, object>? Arguments)> GetCalledToolsWithArgs(EvalItem item)
    {
        var calls = new List<(string Name, IReadOnlyDictionary<string, object>? Arguments)>();

        foreach (var message in item.Conversation)
        {
            foreach (var content in message.Contents)
            {
                if (content is FunctionCallContent functionCall)
                {
                    IDictionary<string, object?>? rawArgs = functionCall.Arguments;
                    IReadOnlyDictionary<string, object>? args = null;
                    if (rawArgs is not null)
                    {
                        var dict = new Dictionary<string, object>(StringComparer.OrdinalIgnoreCase);
                        foreach (var kvp in rawArgs)
                        {
                            if (kvp.Value is not null)
                            {
                                // Normalize JsonElement values to their .NET equivalents for comparison
                                dict[kvp.Key] = kvp.Value is JsonElement je ? UnwrapJsonElement(je) : kvp.Value;
                            }
                        }

                        args = dict;
                    }

                    calls.Add((functionCall.Name, args));
                }
            }
        }

        return calls;
    }

    private static object UnwrapJsonElement(JsonElement element)
    {
        return element.ValueKind switch
        {
            JsonValueKind.String => element.GetString()!,
            JsonValueKind.Number => element.TryGetInt64(out var l) ? l : element.GetDouble(),
            JsonValueKind.True => true,
            JsonValueKind.False => false,
            _ => element.ToString(),
        };
    }
}
