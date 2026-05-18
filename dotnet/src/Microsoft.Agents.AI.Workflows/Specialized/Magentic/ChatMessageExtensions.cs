// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Linq;
using System.Text;
using System.Text.Json;
using System.Text.RegularExpressions;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Workflows.Specialized.Magentic;

internal static partial class ChatMessageExtensions
{
    private static void ProcessAIContents(StringBuilder resultBuilder, IEnumerable<AIContent> contents, StreamingToolCallResultPairMatcher? pairMatcher = null)
    {
        pairMatcher ??= new();

        foreach (AIContent content in contents)
        {
            switch (content)
            {
                case TextContent textContent:
                    resultBuilder.AppendLine(textContent.Text);
                    break;

                //case DataContent dataContent:
                //    // We really do not know how to deal with anything other than image data with descriptions, which is not
                //    // a well-defined concept in MEAI (as contrasted with AutoGen's ImageContent type)
                //    break;

                case ErrorContent errorContent:
                    resultBuilder.AppendLine($"[ERROR{(errorContent.ErrorCode != null ? $"(Code={errorContent.ErrorCode})" : string.Empty)}]");
                    resultBuilder.AppendLine(errorContent.Message);

                    if (errorContent.Details != null)
                    {
                        resultBuilder.Append("Details:").AppendLine(errorContent.Details);
                    }

                    break;

                case FunctionCallContent functionCallContent:
                    pairMatcher.CollectFunctionCall(functionCallContent);
                    break;

                case FunctionResultContent functionResultContent:
                    pairMatcher.TryResolveFunctionCall(functionResultContent, out string? functionName);
                    string result = functionResultContent.Result?.ToString() ?? string.Empty;

                    resultBuilder.AppendLine($"[Tool Call '{functionName ?? functionResultContent.CallId}' Result]")
                                 .AppendLine(result);

                    break;

                case McpServerToolCallContent mstContent:
                    pairMatcher.CollectMcpServerToolCall(mstContent);
                    break;

                case McpServerToolResultContent mstResultContent:
                    if (mstResultContent.Outputs?.Any() is true)
                    {
                        pairMatcher.TryResolveMcpServerToolCall(mstResultContent, out string? mcpServerToolName);
                        resultBuilder.AppendLine($"[Start MCP Server Tool Call '{mcpServerToolName ?? mstResultContent.CallId}' Results]");

                        ProcessAIContents(resultBuilder, mstResultContent.Outputs!);

                        resultBuilder.AppendLine($"[End MCP Server Tool Call '{mcpServerToolName ?? mstResultContent.CallId}']");
                    }

                    break;
                case TextReasoningContent reasoningContent:
                    if (!string.IsNullOrWhiteSpace(reasoningContent.Text))
                    {
                        resultBuilder.Append("[Reasoning] ")
                                     .AppendLine(reasoningContent.Text);
                    }

                    break;

                case UriContent uriContent:
                    resultBuilder.AppendLine(uriContent.Uri.ToString());
                    break;
            }
        }
    }

    public static string GetText(this List<ChatMessage> messages)
    {
        if (messages.Count == 0)
        {
            return string.Empty;
        }

        StringBuilder builder = new();
        StreamingToolCallResultPairMatcher pairMatcher = new();
        foreach (ChatMessage message in messages)
        {
            ProcessAIContents(builder, message.Contents, pairMatcher);
        }

        return builder.ToString();
    }

    private const string FencedJsonRegexPattern = @"```(?<lang>[a-z]+)?\s*(?<json>\{[\s\S]*?\})\s*```";
#if NET
    [GeneratedRegex(FencedJsonRegexPattern, RegexOptions.IgnoreCase | RegexOptions.CultureInvariant | RegexOptions.ExplicitCapture)]
    public static partial Regex FencedJsonRegex();
#else
    public static Regex FencedJsonRegex() => s_fencedJsonRegex;
    private static readonly Regex s_fencedJsonRegex =
        new(FencedJsonRegexPattern, RegexOptions.Compiled | RegexOptions.CultureInvariant | RegexOptions.ExplicitCapture);
#endif

    internal static JsonElement ExtractJson(string messageText)
    {
        Match match = FencedJsonRegex().Match(messageText);
        if (match.Success)
        {
            return JsonElement.Parse(match.Groups["json"].Value);
        }

        int start = messageText.IndexOf('{'), scanHead = start;
        int? end = null;

        if (scanHead < 0)
        {
            throw new InvalidOperationException("No JSON object found.");
        }

        int depth = 0;
        bool inQuotes = false, inEscape = false;
        for (; scanHead < messageText.Length && end is null; scanHead++)
        {
            if (inEscape)
            {
                inEscape = false;
                continue;
            }

            switch (messageText[scanHead])
            {
                case '{' when !inQuotes:
                    depth++;
                    break;
                case '}' when !inQuotes:
                    depth--;
                    if (depth == 0)
                    {
                        end = scanHead;
                    }

                    break;
                case '\"':
                    // We already handled inEscape, so we can always flip inQuotes here
                    inQuotes = !inQuotes;
                    break;
                case '\\':
                    Debug.Assert(!inEscape);
                    inEscape = true;
                    break;
            }
        }

        if (end is null)
        {
            throw new InvalidOperationException("Unbalanced JSON braces.");
        }

        return JsonElement.Parse(messageText.Substring(start, end.Value - start + 1));
    }

    public static JsonElement ExtractJson(this ChatMessage message) => ExtractJson(message.Text);
}
