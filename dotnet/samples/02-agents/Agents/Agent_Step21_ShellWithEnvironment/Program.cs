// Copyright (c) Microsoft. All rights reserved.

using Azure.AI.OpenAI;
using Azure.Identity;
using Microsoft.Agents.AI;
using Microsoft.Agents.AI.Tools.Shell;
using Microsoft.Extensions.AI;
using OpenAI.Chat;

var endpoint = Environment.GetEnvironmentVariable("AZURE_OPENAI_ENDPOINT") ?? throw new InvalidOperationException("AZURE_OPENAI_ENDPOINT is not set.");
var deploymentName = Environment.GetEnvironmentVariable("AZURE_OPENAI_DEPLOYMENT_NAME") ?? "gpt-5.4-mini";

var chatClient = new AzureOpenAIClient(new Uri(endpoint), new DefaultAzureCredential())
    .GetChatClient(deploymentName);

const string Instructions = """
    You are an agent with a single tool: run_shell. Use it to satisfy the
    user's request. Do not describe what you would do — actually run the
    commands. Reply with the final answer derived from real output.
    """;

// --------------------------------------------------------------------
// 1. Stateless mode — each call gets a fresh shell.
// --------------------------------------------------------------------
Console.WriteLine("### Stateless mode\n");
await using (var statelessShell = new LocalShellTool(mode: ShellMode.Stateless, acknowledgeUnsafe: true))
{
    var envProvider = new ShellEnvironmentProvider(statelessShell);
    var statelessAgent = chatClient.AsAIAgent(new ChatClientAgentOptions
    {
        ChatOptions = new()
        {
            Instructions = Instructions,
            Tools = [statelessShell.AsAIFunction(requireApproval: false)],
        },
        AIContextProviders = [envProvider],
    });

    var statelessSession = await statelessAgent.CreateSessionAsync();
    Console.WriteLine(await statelessAgent.RunAsync("Print the current working directory.", statelessSession));
    Console.WriteLine();
    Console.WriteLine(await statelessAgent.RunAsync("Print the value of the PATH environment variable, truncated to the first 200 characters.", statelessSession));
    Console.WriteLine();

    PrintSnapshot(envProvider.CurrentSnapshot!);
}

// --------------------------------------------------------------------
// 2. Persistent mode — one shell, reused across calls. State carries.
// --------------------------------------------------------------------
Console.WriteLine("\n### Persistent mode\n");
await using (var persistentShell = new LocalShellTool(mode: ShellMode.Persistent, acknowledgeUnsafe: true))
{
    var envProvider = new ShellEnvironmentProvider(persistentShell);
    var persistentAgent = chatClient.AsAIAgent(new ChatClientAgentOptions
    {
        ChatOptions = new()
        {
            Instructions = Instructions,
            Tools = [persistentShell.AsAIFunction(requireApproval: false)],
        },
        AIContextProviders = [envProvider],
    });

    var persistentSession = await persistentAgent.CreateSessionAsync();
    Console.WriteLine(await persistentAgent.RunAsync("Set the environment variable DEMO_TOKEN to the value 'hello-world'.", persistentSession));
    Console.WriteLine();
    Console.WriteLine(await persistentAgent.RunAsync("Print the current value of DEMO_TOKEN. Tell me exactly what value the shell reports.", persistentSession));
    Console.WriteLine();

    PrintSnapshot(envProvider.CurrentSnapshot!);
}

static void PrintSnapshot(ShellEnvironmentSnapshot snap)
{
    Console.WriteLine("--- Captured environment snapshot ---");
    Console.WriteLine($"  Family:  {snap.Family}");
    Console.WriteLine($"  OS:      {snap.OSDescription}");
    Console.WriteLine($"  Shell:   {snap.ShellVersion ?? "(unknown)"}");
    Console.WriteLine($"  CWD:     {snap.WorkingDirectory}");
    foreach (var (tool, version) in snap.ToolVersions)
    {
        Console.WriteLine($"  {tool,-8} {version ?? "(not installed)"}");
    }
}
