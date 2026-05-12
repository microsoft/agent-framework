// Copyright (c) Microsoft. All rights reserved.

// Shell tool with environment-aware system prompt
//
// WARNING: This sample uses LocalShellExecutor, which executes real commands
// against the shell on this machine. Approval gating is disabled here so
// the demo runs unattended; in any real application keep approval on
// (the default), or use DockerShellExecutor for container isolation. The
// commands the model emits below are read-only or scoped (echo, cd into
// a temp folder, set a process-local env var) but a different model or
// prompt could choose to do something destructive. Run this only in an
// environment where you are comfortable with the agent typing into your
// terminal.
//
// Demonstrates LocalShellExecutor in both modes paired with
// ShellEnvironmentProvider, an AIContextProvider that probes the live
// shell (OS, family, version, CWD, common CLIs) and injects authoritative
// system-prompt instructions so the agent emits commands in the right
// idiom (PowerShell vs POSIX).
//
// Two runs:
//   1) Stateless mode: each tool call runs in a fresh shell. Useful when
//      commands are independent (read-only scripts, version checks, file
//      listings) and you want strong isolation between calls. Side
//      effects in one call (cd, exported variables) do NOT carry to the
//      next.
//   2) Persistent mode: a single long-lived shell is reused across calls,
//      so working directory and exported environment variables are
//      preserved. Useful for multi-step workflows that build state
//      (cd into a folder and run a sequence of commands there; set a
//      token in one step and read it in the next).

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
await using (var statelessShell = new LocalShellExecutor(new() { Mode = ShellMode.Stateless, AcknowledgeUnsafe = true }))
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

    // Show that side effects do NOT carry between stateless calls: ask the
    // agent to cd into the system temp directory in one call, then ask
    // for the CWD in a second call. Stateless mode means the cd is gone.
    Console.WriteLine(await statelessAgent.RunAsync("Change directory into the system temp folder, then print the current working directory.", statelessSession));
    Console.WriteLine();
    Console.WriteLine(await statelessAgent.RunAsync("In a NEW shell call, print the current working directory again. Tell me whether it matches the temp folder from the previous call.", statelessSession));
    Console.WriteLine();

    PrintSnapshot(envProvider.CurrentSnapshot!);
}

// --------------------------------------------------------------------
// 2. Persistent mode — one shell, reused across calls. State carries.
// --------------------------------------------------------------------
Console.WriteLine("\n### Persistent mode\n");
await using (var persistentShell = new LocalShellExecutor(new() { Mode = ShellMode.Persistent, AcknowledgeUnsafe = true }))
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

    // State carries across calls in persistent mode: cd into temp, then
    // verify the next call sees the new CWD.
    Console.WriteLine(await persistentAgent.RunAsync("Change directory into the system temp folder, then print the current working directory.", persistentSession));
    Console.WriteLine();
    Console.WriteLine(await persistentAgent.RunAsync("In a NEW shell call, print the current working directory again. Tell me whether it still matches the temp folder.", persistentSession));
    Console.WriteLine();

    // Same idea with an exported variable: set in one call, read in the next.
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
