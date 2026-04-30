// Copyright (c) Microsoft. All rights reserved.

// This sample demonstrates using FileSystemTool with a ChatClientAgent, including human approval for destructive operations.

using Azure.AI.OpenAI;
using Azure.Identity;
using Microsoft.Agents.AI;
using Microsoft.Extensions.AI;
using OpenAI.Chat;
using ChatMessage = Microsoft.Extensions.AI.ChatMessage;

var endpoint = Environment.GetEnvironmentVariable("AZURE_OPENAI_ENDPOINT") ?? throw new InvalidOperationException("AZURE_OPENAI_ENDPOINT is not set.");
var deploymentName = Environment.GetEnvironmentVariable("AZURE_OPENAI_DEPLOYMENT_NAME") ?? "gpt-5.4-mini";
var workspace = Environment.GetEnvironmentVariable("FILESYSTEM_TOOL_WORKSPACE") ?? Environment.CurrentDirectory;

var fileSystem = new FileSystemTool(
    workspace,
    new FileSystemPolicy
    {
        WritePaths = ["scratch/**", "notes/**"],
    });

// WARNING: DefaultAzureCredential is convenient for development but requires careful consideration in production.
// In production, consider using a specific credential (e.g., ManagedIdentityCredential) to avoid
// latency issues, unintended credential probing, and potential security risks from fallback mechanisms.
AIAgent agent = new AzureOpenAIClient(new Uri(endpoint), new DefaultAzureCredential())
    .GetChatClient(deploymentName)
    .AsAIAgent(
        instructions: "You are a helpful assistant. Use the filesystem tools only inside the configured workspace.",
        tools: fileSystem.AsTools());

AgentSession session = await agent.CreateSessionAsync();
AgentResponse response = await agent.RunAsync(
    "Create scratch/example.txt, then use fs_multi_edit to replace a word twice. Ask before deleting, moving, or renaming files.",
    session);

List<ToolApprovalRequestContent> approvalRequests = GetApprovalRequests(response);
while (approvalRequests.Count > 0)
{
    List<ChatMessage> approvals = approvalRequests.ConvertAll(request =>
    {
        var call = (FunctionCallContent)request.ToolCall;
        Console.WriteLine($"Approve filesystem operation '{call.Name}'? Reply Y to approve:");
        bool approved = Console.ReadLine()?.Equals("Y", StringComparison.OrdinalIgnoreCase) ?? false;
        return new ChatMessage(ChatRole.User, [request.CreateResponse(approved)]);
    });

    response = await agent.RunAsync(approvals, session);
    approvalRequests = GetApprovalRequests(response);
}

Console.WriteLine($"\nAgent: {response}");

static List<ToolApprovalRequestContent> GetApprovalRequests(AgentResponse response)
    => response.Messages.SelectMany(message => message.Contents).OfType<ToolApprovalRequestContent>().ToList();
