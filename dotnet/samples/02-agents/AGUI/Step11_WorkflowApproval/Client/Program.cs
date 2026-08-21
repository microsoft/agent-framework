// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json;
using AGUI.Client;
using Microsoft.Extensions.AI;

string serverUrl = Environment.GetEnvironmentVariable("AGUI_SERVER_URL") ?? "http://localhost:8888";
using HttpClient httpClient = new() { Timeout = TimeSpan.FromSeconds(60) };
using IChatClient chatClient = CreateChatClient(httpClient, serverUrl);
ChatOptions options = new();

var expenseReport = new
{
    id = "EXP-100",
    employee = "Taylor",
    amount = 125.00m,
    businessPurpose = "Developer conference registration",
    receiptAttached = true,
};
string reportJson = JsonSerializer.Serialize(expenseReport);

List<ChatResponseUpdate> firstTurn = await chatClient
    .GetStreamingResponseAsync(
        [new ChatMessage(ChatRole.User, $"Review and submit this expense report:\n{reportJson}")],
        options)
    .ToListAsync();

#pragma warning disable MEAI001 // Tool approval content is experimental.
ToolApprovalRequestContent approvalRequest = firstTurn
    .SelectMany(static update => update.Contents)
    .OfType<ToolApprovalRequestContent>()
    .Single();
FunctionCallContent toolCall = (FunctionCallContent)approvalRequest.ToolCall;

Console.WriteLine($"The workflow completed its checks and wants to call {toolCall.Name}.");
Console.Write($"Approve submission of expense {expenseReport.id}? [y/N]: ");
bool approved = string.Equals(Console.ReadLine(), "y", StringComparison.OrdinalIgnoreCase);
ToolApprovalResponseContent approvalResponse = approvalRequest.CreateResponse(
    approved,
    approved ? "Approved by the sample user." : "Rejected by the sample user.");

List<ChatMessage> approvalMessages =
[
    new(ChatRole.Assistant, [approvalRequest]),
    new(ChatRole.Tool, [approvalResponse]),
];

await foreach (ChatResponseUpdate update in chatClient.GetStreamingResponseAsync(approvalMessages, options))
{
    foreach (TextContent text in update.Contents.OfType<TextContent>())
    {
        Console.Write(text.Text);
    }
}
#pragma warning restore MEAI001

Console.WriteLine();

static IChatClient CreateChatClient(HttpClient httpClient, string serverUrl)
    => new AGUIChatClient(new(httpClient, serverUrl));
