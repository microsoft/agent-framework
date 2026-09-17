// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI;

/// <summary>
/// Shared helpers for deciding whether a tool call is subject to human approval.
/// </summary>
/// <remarks>
/// <para>
/// <see cref="FunctionInvokingChatClient"/> has an all-or-nothing behavior for approvals: when any tool in a
/// response is an <see cref="ApprovalRequiredAIFunction"/>, every <see cref="FunctionCallContent"/> in that
/// response is converted to a <see cref="ToolApprovalRequestContent"/>, including calls to tools that do not
/// require approval. Several decorators therefore need to tell the two apart, and they must agree on the answer.
/// </para>
/// <para>
/// The rule is deliberately closed by default: a tool counts as not requiring approval only when it is a known
/// tool that is explicitly not an <see cref="ApprovalRequiredAIFunction"/>. Anything else, including a tool name
/// that does not appear in the available tools at all, is treated as requiring approval.
/// </para>
/// </remarks>
internal static class ApprovalRequirement
{
    /// <summary>
    /// Builds the set of tool names that do not require approval, from the tools available to this turn:
    /// <see cref="ChatOptions.Tools"/> together with <see cref="FunctionInvokingChatClient.AdditionalTools"/>.
    /// </summary>
    /// <param name="client">The decorator requesting the set, used to locate the <see cref="FunctionInvokingChatClient"/> below it in the pipeline.</param>
    /// <param name="options">The options for the current request, if any.</param>
    public static HashSet<string> GetApprovalNotRequiredToolNames(IChatClient client, ChatOptions? options)
    {
        var ficc = client.GetService<FunctionInvokingChatClient>();

        var allTools = (options?.Tools ?? Enumerable.Empty<AITool>())
            .Concat(ficc?.AdditionalTools ?? Enumerable.Empty<AITool>());

        return new HashSet<string>(
            allTools
                .OfType<AIFunction>()
                .Where(static f => f.GetService<ApprovalRequiredAIFunction>() is null)
                .Select(static f => f.Name),
            StringComparer.Ordinal);
    }

    /// <summary>
    /// Determines whether a tool call targets a known tool that does not require approval.
    /// </summary>
    /// <param name="toolCall">The tool call carried by an approval request or response.</param>
    /// <param name="approvalNotRequiredToolNames">The set produced by <see cref="GetApprovalNotRequiredToolNames"/>.</param>
    /// <returns>
    /// <see langword="true"/> only when <paramref name="toolCall"/> is a function call whose tool is known and
    /// explicitly does not require approval; otherwise <see langword="false"/>, which includes unknown tools and
    /// non-function tool calls.
    /// </returns>
    public static bool IsApprovalNotRequired(AIContent? toolCall, HashSet<string> approvalNotRequiredToolNames)
        => toolCall is FunctionCallContent functionCall && approvalNotRequiredToolNames.Contains(functionCall.Name);
}
