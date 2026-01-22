// Copyright (c) Microsoft. All rights reserved.

// This sample demonstrates how to use the ShellTool with an AI agent.
// It shows security configuration options and human-in-the-loop approval for shell commands.
//
// SECURITY NOTE: The ShellTool executes real shell commands on your system.
// Always configure appropriate security restrictions before use.

using Azure.AI.OpenAI;
using Azure.Identity;
using Microsoft.Agents.AI;
using Microsoft.Extensions.AI;
using OpenAI.Chat;
using ChatMessage = Microsoft.Extensions.AI.ChatMessage;

var endpoint = Environment.GetEnvironmentVariable("AZURE_OPENAI_ENDPOINT")
    ?? throw new InvalidOperationException("AZURE_OPENAI_ENDPOINT is not set.");
var deploymentName = Environment.GetEnvironmentVariable("AZURE_OPENAI_DEPLOYMENT_NAME") ?? "gpt-4o-mini";

// Get a temporary working directory for the shell tool
var workingDirectory = Path.Combine(Path.GetTempPath(), "shell-tool-sample");
Directory.CreateDirectory(workingDirectory);

Console.WriteLine($"Working directory: {workingDirectory}");
Console.WriteLine();

// Create the shell tool with security options.
// This configuration restricts what commands can be executed.
var shellTool = new ShellTool(
    executor: new LocalShellExecutor(),
    options: new ShellToolOptions
    {
        // Set the working directory for command execution
        WorkingDirectory = workingDirectory,

        // Restrict file system access to specific paths
        AllowedPaths = [workingDirectory],

        // Block access to sensitive paths (takes priority over AllowedPaths)
        // BlockedPaths = ["/etc", "/var"],

        // Only allow specific commands (regex patterns supported)
        AllowedCommands = ["^ls", "^dir", "^echo", "^cat", "^type", "^mkdir", "^pwd", "^cd"],

        // Block dangerous patterns (enabled by default)
        BlockDangerousPatterns = true,

        // Block command chaining operators like ; | && || (enabled by default)
        BlockCommandChaining = true,

        // Block privilege escalation commands like sudo, su (enabled by default)
        BlockPrivilegeEscalation = true,

        // Set execution timeout (default: 60 seconds)
        TimeoutInMilliseconds = 30000,

        // Set maximum output size (default: 50KB)
        MaxOutputLength = 10240
    });

// Convert the shell tool to an AIFunction for use with agents.
// Wrap with ApprovalRequiredAIFunction to require user approval before execution.
var shellFunction = new ApprovalRequiredAIFunction(shellTool.AsAIFunction());

// Detect platform for shell command guidance
var operatingSystem = OperatingSystem.IsWindows() ? "Windows" : "Unix/Linux";

// Create the chat client and agent with the shell tool.
AIAgent agent = new AzureOpenAIClient(
    new Uri(endpoint),
    new AzureCliCredential())
    .GetChatClient(deploymentName)
    .AsAIAgent(
        instructions: $"""
            You are a helpful assistant with access to a shell tool.
            You can execute shell commands to help the user with file system tasks.
            Always explain what commands you're about to run before executing them.
            The working directory is a temporary folder, so feel free to create files and folders there.
            The operating system is {operatingSystem}.
            """,
        tools: [shellFunction]);

Console.WriteLine("Agent with Shell Tool");
Console.WriteLine("=====================");
Console.WriteLine("This agent can execute shell commands with security restrictions.");
Console.WriteLine("Commands require user approval before execution.");
Console.WriteLine();

// Interactive conversation loop
AgentThread thread = await agent.GetNewThreadAsync();

while (true)
{
    Console.Write("You: ");
    var userInput = Console.ReadLine();

    if (string.IsNullOrWhiteSpace(userInput) || userInput.Equals("exit", StringComparison.OrdinalIgnoreCase))
    {
        break;
    }

    var response = await agent.RunAsync(userInput, thread);
    var userInputRequests = response.UserInputRequests.ToList();

    // Handle approval requests for shell commands
    while (userInputRequests.Count > 0)
    {
        var userInputResponses = userInputRequests
            .OfType<FunctionApprovalRequestContent>()
            .Select(functionApprovalRequest =>
            {
                Console.WriteLine();
                Console.WriteLine($"[APPROVAL REQUIRED] The agent wants to execute: {functionApprovalRequest.FunctionCall.Name}");

                // Display the commands that will be executed
                var arguments = functionApprovalRequest.FunctionCall.Arguments;
                if (arguments is not null && arguments.TryGetValue("commands", out var commands) && commands is not null)
                {
                    Console.WriteLine($"Commands: {commands}");
                }

                Console.Write("Approve? (Y/N): ");
                var approved = Console.ReadLine()?.Equals("Y", StringComparison.OrdinalIgnoreCase) ?? false;

                return new ChatMessage(ChatRole.User, [functionApprovalRequest.CreateResponse(approved)]);
            })
            .ToList();

        response = await agent.RunAsync(userInputResponses, thread);
        userInputRequests = response.UserInputRequests.ToList();
    }

    Console.WriteLine();
    Console.WriteLine($"Agent: {response}");
    Console.WriteLine();
}
