// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.AI;
using Microsoft.Extensions.AI;

namespace Harness.Shared.Console.Observers;

/// <summary>
/// Collects <see cref="ToolApprovalRequestContent"/> items during the response stream,
/// displays approval-needed notifications inline, and prompts the user for approval
/// decisions after the stream completes.
/// </summary>
internal sealed class ToolApprovalObserver : ConsoleObserver
{
    private readonly List<ToolApprovalRequestContent> _approvalRequests = [];

    /// <inheritdoc/>
    public override async Task OnContentAsync(HarnessUXContainer ux, AIContent content)
    {
        if (content is ToolApprovalRequestContent approvalRequest)
        {
            this._approvalRequests.Add(approvalRequest);
            string toolName = approvalRequest.ToolCall is FunctionCallContent fc
                ? ToolCallFormatter.Format(fc)
                : approvalRequest.ToolCall?.ToString() ?? "unknown";
            await ux.WriteInfoLineAsync($"⚠️ Approval needed: {toolName}", ConsoleColor.Yellow);
        }
    }

    /// <inheritdoc/>
    public override async Task<IList<ChatMessage>?> OnStreamCompleteAsync(
        HarnessUXContainer ux,
        AIAgent agent,
        AgentSession session,
        HarnessConsoleOptions options)
    {
        if (this._approvalRequests.Count == 0)
        {
            return null;
        }

        var messages = await PromptForApprovalsAsync(ux, this._approvalRequests);
        this._approvalRequests.Clear();
        return messages;
    }

    private static async Task<List<ChatMessage>?> PromptForApprovalsAsync(HarnessUXContainer ux, List<ToolApprovalRequestContent> approvalRequests)
    {
        if (approvalRequests.Count == 0)
        {
            return null;
        }

        var responses = new List<AIContent>();
        foreach (var request in approvalRequests)
        {
            string toolName = request.ToolCall is FunctionCallContent fc
                ? ToolCallFormatter.Format(fc)
                : request.ToolCall?.ToString() ?? "unknown";

            var choices = new List<string>
            {
                "Approve this call",
                "Always approve this tool (any arguments)",
                "Always approve this tool with these arguments",
                "Deny",
            };

            string selection = await ux.ReadSelectionAsync($"🔐 Tool approval: {toolName}", choices);
            AIContent response = selection switch
            {
                "Always approve this tool (any arguments)" => request.CreateAlwaysApproveToolResponse("User chose to always approve this tool"),
                "Always approve this tool with these arguments" => request.CreateAlwaysApproveToolWithArgumentsResponse("User chose to always approve this tool with these arguments"),
                "Deny" => request.CreateResponse(approved: false, reason: "User denied"),
                _ => request.CreateResponse(approved: true, reason: "User approved"),
            };

            string action = selection switch
            {
                "Always approve this tool (any arguments)" => "✅ Always approved (any args)",
                "Always approve this tool with these arguments" => "✅ Always approved (these args)",
                "Deny" => "❌ Denied",
                _ => "✅ Approved",
            };
            await ux.WriteInfoLineAsync($"   {action}", ConsoleColor.DarkGray);

            responses.Add(response);
        }

        return [new ChatMessage(ChatRole.User, responses)];
    }
}
