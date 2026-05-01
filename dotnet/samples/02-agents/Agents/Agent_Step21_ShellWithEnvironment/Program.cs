// Copyright (c) Microsoft. All rights reserved.

using Azure.AI.OpenAI;
using Azure.Identity;
using Microsoft.Agents.AI;
using Microsoft.Agents.AI.Tools.Shell;
using Microsoft.Extensions.AI;
using OpenAI.Chat;

var endpoint = Environment.GetEnvironmentVariable("AZURE_OPENAI_ENDPOINT") ?? throw new InvalidOperationException("AZURE_OPENAI_ENDPOINT is not set.");
var deploymentName = Environment.GetEnvironmentVariable("AZURE_OPENAI_DEPLOYMENT_NAME") ?? "gpt-5.4-mini";

// A persistent shell session preserves env vars across tool calls — exactly
// what makes OS-mismatch bugs visible: the model must use platform-native
// syntax to set a var in call N and read it back in call N+1.
// Sample is unattended: opt out of approval gating. In a real app you'd
// either keep approvals on, or run inside DockerShellTool for isolation.
await using var shell = new LocalShellTool(mode: ShellMode.Persistent, acknowledgeUnsafe: true);
var envProvider = new ShellEnvironmentProvider(shell);

AIAgent agent = new AzureOpenAIClient(new Uri(endpoint), new DefaultAzureCredential())
    .GetChatClient(deploymentName)
    .AsAIAgent(new ChatClientAgentOptions()
    {
        ChatOptions = new()
        {
            Instructions = """
            You are an agent with a single tool: run_shell. Use it to satisfy the
            user's request. Do not describe what you would do — actually run the
            commands. Reply with the final answer derived from real output.
            """,
            Tools = [shell.AsAIFunction(requireApproval: false)],
        },
        AIContextProviders = [envProvider],
    });

AgentSession session = await agent.CreateSessionAsync();

Console.WriteLine("=== Run 1: set DEMO_TOKEN ===");
Console.WriteLine(await agent.RunAsync("Set the environment variable DEMO_TOKEN to the value 'hello-world'.", session));

Console.WriteLine("\n=== Run 2: read DEMO_TOKEN back in a new shell call ===");
Console.WriteLine(await agent.RunAsync("Print the current value of the DEMO_TOKEN environment variable. Tell me exactly what value the shell reports.", session));

Console.WriteLine("\n=== Captured environment snapshot ===");
var snap = envProvider.CurrentSnapshot!;
Console.WriteLine($"  Family:  {snap.Family}");
Console.WriteLine($"  OS:      {snap.OSDescription}");
Console.WriteLine($"  Shell:   {snap.ShellVersion ?? "(unknown)"}");
Console.WriteLine($"  CWD:     {snap.WorkingDirectory}");
foreach (var (tool, version) in snap.ToolVersions)
{
    Console.WriteLine($"  {tool,-8} {version ?? "(not installed)"}");
}
