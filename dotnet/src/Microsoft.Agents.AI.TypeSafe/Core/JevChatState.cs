// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json;
using System.Text.Json.Nodes;
using Microsoft.Extensions.AI;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI.TypeSafe;

/// <summary>
/// Converts a conversation into the state that Jev answers questions about, and reads the current turn of it.
/// </summary>
/// <remarks>
/// The state has the shape of the Python TypeSafe connector: <c>{"messages": [{"role", "contents": [...]}],
/// "instructions"}</c>, where each content is <c>text</c>, <c>text_reasoning</c>, <c>function_call</c>, or
/// <c>function_result</c>. Tool approval requests and responses are left out: they are control messages, and the call
/// and result they lead to carry the information. The current turn is everything after the last user message that
/// starts a request: the tool calls and results that answer it.
/// </remarks>
internal static class JevChatState
{
    public static JevEntry Build(IReadOnlyList<ChatMessage> messages, string? instructions)
    {
        var stateMessages = new JsonArray();
        for (int index = 0; index < messages.Count; index++)
        {
            ChatMessage message = messages[index];
            List<string> unsupported = [.. message.Contents
                .Where(content => content is not (TextContent or TextReasoningContent or FunctionCallContent or FunctionResultContent or ToolApprovalRequestContent or ToolApprovalResponseContent))
                .Select(content => content.GetType().Name)
                .Distinct(StringComparer.Ordinal)
                .OrderBy(name => name, StringComparer.Ordinal)];
            if (unsupported.Count > 0)
            {
                throw new NotSupportedException(
                    $"Jev supports text, reasoning text, and function call and result content only; message {index} contains {string.Join(", ", unsupported)}.");
            }

            // Approval content is not written: FunctionInvokingChatClient keeps handled approvals in the history of
            // later turns, and rejecting them would make every turn after an approval fail.
            var contents = new JsonArray();
            foreach (AIContent content in message.Contents)
            {
                switch (content)
                {
                    case TextContent { Text: { Length: > 0 } text }:
                        contents.Add((JsonNode)new JsonObject { ["type"] = "text", ["text"] = text });
                        break;

                    // Only the readable reasoning text is sent; protected (encrypted) reasoning is meaningful only to
                    // the model that produced it.
                    case TextReasoningContent { Text: { Length: > 0 } reasoning }:
                        contents.Add((JsonNode)new JsonObject { ["type"] = "text_reasoning", ["text"] = reasoning });
                        break;

                    case FunctionCallContent call:
                        contents.Add((JsonNode)new JsonObject
                        {
                            ["type"] = "function_call",
                            ["call_id"] = call.CallId,
                            ["name"] = call.Name,
                            ["arguments"] = call.Arguments is null ? null : ToObject(call.Arguments),
                        });
                        break;

                    case FunctionResultContent result:
                        contents.Add((JsonNode)SerializeResult(result));
                        break;
                }
            }

            if (contents.Count > 0)
            {
                stateMessages.Add((JsonNode)new JsonObject { ["role"] = message.Role.Value, ["contents"] = contents });
            }
        }

        if (stateMessages.Count == 0)
        {
            Throw.ArgumentException(nameof(messages), "Jev needs at least one message with text or function call content.");
        }

        var state = new JsonObject { ["messages"] = stateMessages };
        if (!string.IsNullOrWhiteSpace(instructions))
        {
            state["instructions"] = instructions;
        }

        return new JevEntry(JevJsonUtilities.Parse(state.ToJsonString()));
    }

    /// <summary>
    /// Gets the index of the first message of the current turn, which follows the last user message that starts a
    /// request.
    /// </summary>
    /// <remarks>
    /// User messages that directly follow a function result continue the turn instead of starting one.
    /// FunctionInvokingChatClient moves text that was sent together with an approval response, such as "Yes, go
    /// ahead", after the approved call and its result. Starting the turn there would hide the approved call from the
    /// tool call limit and offer the tool again with no hint that it already ran.
    /// </remarks>
    public static int GetCurrentTurnStart(IReadOnlyList<ChatMessage> messages)
    {
        int index = messages.Count - 1;
        while (index >= 0)
        {
            if (messages[index].Role != ChatRole.User)
            {
                index--;
                continue;
            }

            // Text that followed several approval responses may span consecutive user messages.
            int runStart = index;
            while (runStart > 0 && messages[runStart - 1].Role == ChatRole.User)
            {
                runStart--;
            }

            if (runStart > 0 && messages[runStart - 1].Contents.Any(content => content is FunctionResultContent))
            {
                index = runStart - 1;
                continue;
            }

            return index + 1;
        }

        return 0;
    }

    /// <summary>Gets the argument sets of the calls in the current turn, by tool name, oldest first.</summary>
    public static Dictionary<string, List<Dictionary<string, JsonElement>>> GetCurrentTurnCalls(IReadOnlyList<ChatMessage> messages, int turnStart)
    {
        var calls = new Dictionary<string, List<Dictionary<string, JsonElement>>>(StringComparer.Ordinal);
        foreach (FunctionCallContent call in CurrentTurnContents<FunctionCallContent>(messages, turnStart))
        {
            if (string.IsNullOrEmpty(call.Name))
            {
                continue;
            }

            var arguments = new Dictionary<string, JsonElement>(StringComparer.Ordinal);
            foreach (KeyValuePair<string, object?> argument in call.Arguments ?? new Dictionary<string, object?>())
            {
                arguments[argument.Key] = JevJsonUtilities.ToElement(argument.Value);
            }

            if (!calls.TryGetValue(call.Name, out List<Dictionary<string, JsonElement>>? list))
            {
                calls[call.Name] = list = [];
            }

            list.Add(arguments);
        }

        return calls;
    }

    /// <summary>Counts the function calls in the current turn.</summary>
    public static int CountCurrentTurnCalls(IReadOnlyList<ChatMessage> messages, int turnStart) =>
        CurrentTurnContents<FunctionCallContent>(messages, turnStart).Count();

    /// <summary>
    /// Gets the text of each function result in the current turn, oldest first, unwrapping results of the form
    /// <c>{"result": "text"}</c>.
    /// </summary>
    public static List<string> GetCurrentTurnResultTexts(IReadOnlyList<ChatMessage> messages, int turnStart) =>
        [.. CurrentTurnContents<FunctionResultContent>(messages, turnStart).Select(result => GetResultText(result.Result)).OfType<string>()];

    private static IEnumerable<T> CurrentTurnContents<T>(IReadOnlyList<ChatMessage> messages, int turnStart)
        where T : AIContent
    {
        for (int index = turnStart; index < messages.Count; index++)
        {
            foreach (T content in messages[index].Contents.OfType<T>())
            {
                yield return content;
            }
        }
    }

    private static JsonObject ToObject(IDictionary<string, object?> arguments)
    {
        var json = new JsonObject();
        foreach (KeyValuePair<string, object?> argument in arguments)
        {
            json[argument.Key] = JevJsonUtilities.ToNodeOrText(argument.Value);
        }

        return json;
    }

    private static JsonObject SerializeResult(FunctionResultContent result)
    {
        var json = new JsonObject { ["type"] = "function_result", ["call_id"] = result.CallId };
        IEnumerable<AIContent>? items = result.Result switch
        {
            AIContent content => [content],
            IEnumerable<AIContent> contents => contents,
            _ => null,
        };

        if (items is null)
        {
            json["result"] = JevJsonUtilities.ToNodeOrText(result.Result);
            return json;
        }

        // Rich results are sent as text items, like the Python connector; other media cannot be described to Jev.
        var texts = new List<string>();
        foreach (AIContent item in items)
        {
            if (item is not TextContent text)
            {
                throw new NotSupportedException($"Jev supports text function results only; a result of the call '{result.CallId}' contains {item.GetType().Name}.");
            }

            texts.Add(text.Text ?? string.Empty);
        }

        json["result"] = string.Concat(texts);
        var textItems = new JsonArray();
        foreach (string text in texts)
        {
            textItems.Add((JsonNode)new JsonObject { ["type"] = "text", ["text"] = text });
        }

        json["items"] = textItems;
        return json;
    }

    private static string? GetResultText(object? result) =>
        result switch
        {
            null => null,
            string text => Unwrap(text),
            JsonElement { ValueKind: JsonValueKind.String } element => Unwrap(element.GetString()!),
            JsonElement { ValueKind: JsonValueKind.Null or JsonValueKind.Undefined } => null,
            JsonElement element => Unwrap(element.GetRawText()),
            TextContent content => content.Text,
            IEnumerable<AIContent> contents => string.Concat(contents.OfType<TextContent>().Select(content => content.Text)),
            _ => JevJsonUtilities.ToNodeOrText(result)?.ToJsonString(),
        };

    /// <summary>
    /// Returns the text of a result written as <c>{"result": "text"}</c>, such as an MCP tool result, or the result
    /// unchanged.
    /// </summary>
    private static string Unwrap(string result)
    {
        if (!result.AsSpan().TrimStart().StartsWith("{".AsSpan(), StringComparison.Ordinal))
        {
            return result;
        }

        try
        {
            using JsonDocument document = JsonDocument.Parse(result);
            JsonElement root = document.RootElement;
            if (root.ValueKind == JsonValueKind.Object &&
                root.EnumerateObject().Count() == 1 &&
                root.TryGetProperty("result", out JsonElement inner) &&
                inner.ValueKind == JsonValueKind.String)
            {
                return inner.GetString()!;
            }
        }
        catch (JsonException)
        {
            // Text that only looks like JSON is returned as it is.
        }

        return result;
    }
}
