// Copyright (c) Microsoft. All rights reserved.

// Agent Mode — Switch an agent's operating mode at runtime with AgentModeProvider
//
// This sample shows how to use the AgentModeProvider, an AIContextProvider that tracks the
// agent's current operating "mode" in the session state and exposes tools (mode_get / mode_set)
// so the agent can query and switch modes as its work progresses. The mode is folded into the
// instructions sent to the model on every turn, so different modes can drive different behavior.
//
// The sample demonstrates two things:
//   1. The built-in default modes ("plan" and "execute") that ship with the provider.
//   2. How to customize the available modes via AgentModeProviderOptions.
//
// It runs a simple interactive loop. In addition to chatting with the agent, you can switch the
// agent's mode yourself using a slash command:
//   /mode            — show the current mode
//   /mode <name>     — switch to the named mode
//   /help            — list the available commands and modes
//   /exit            — quit
//
// When you switch modes with /mode, the provider injects a notification on the next turn so the
// agent clearly sees the change and adjusts its behavior accordingly.

using Azure.AI.Projects;
using Azure.Identity;
using Microsoft.Agents.AI;
using Microsoft.Extensions.AI;

var endpoint = Environment.GetEnvironmentVariable("FOUNDRY_PROJECT_ENDPOINT") ?? throw new InvalidOperationException("FOUNDRY_PROJECT_ENDPOINT is not set.");
var model = Environment.GetEnvironmentVariable("FOUNDRY_MODEL") ?? "gpt-5.4-mini";

// Set AGENT_MODE_USE_CUSTOM=true to run the sample with the custom modes defined below instead of
// the provider's built-in "plan" / "execute" defaults.
bool useCustomModes = string.Equals(Environment.GetEnvironmentVariable("AGENT_MODE_USE_CUSTOM"), "true", StringComparison.OrdinalIgnoreCase);

// <create_mode_provider>
AgentModeProvider modeProvider;
string[] availableModes;

if (useCustomModes)
{
    // Customize the set of modes by supplying AgentModeProviderOptions. Each mode has a name and a
    // block of instructions describing how the agent should behave while operating in that mode.
    // DefaultMode selects the mode new sessions start in (defaults to the first mode when omitted).
    modeProvider = new AgentModeProvider(new AgentModeProviderOptions
    {
        DefaultMode = "concise",
        Modes =
        [
            new AgentModeProviderOptions.AgentMode(
                "concise",
                "Answer in a single short sentence. Do not elaborate unless the user explicitly asks for more detail."),
            new AgentModeProviderOptions.AgentMode(
                "detailed",
                "Answer thoroughly. Explain your reasoning, provide examples, and cover relevant edge cases."),
        ],
    });

    availableModes = ["concise", "detailed"];
}
else
{
    // Use the provider's built-in modes: "plan" (interactive planning) and "execute" (autonomous
    // execution). No options are required.
    modeProvider = new AgentModeProvider();
    availableModes = ["plan", "execute"];
}
// </create_mode_provider>

// Create the agent and attach the mode provider as an AIContextProvider.
// WARNING: DefaultAzureCredential is convenient for development but requires careful consideration in production.
// In production, consider using a specific credential (e.g., ManagedIdentityCredential) to avoid
// latency issues, unintended credential probing, and potential security risks from fallback mechanisms.
AIAgent agent = new AIProjectClient(new Uri(endpoint), new DefaultAzureCredential())
    .AsAIAgent(new ChatClientAgentOptions
    {
        Name = "ModeAwareAssistant",
        ChatOptions = new ChatOptions
        {
            ModelId = model,
            Instructions = "You are a helpful assistant. Follow the process and behavior required by your current operating mode.",
        },
        AIContextProviders = [modeProvider],
    });

using var providerToDispose = modeProvider;

AgentSession session = await agent.CreateSessionAsync();

Console.WriteLine("Agent Mode sample. Type a message to chat, or use a slash command.");
Console.WriteLine($"Available modes: {string.Join(", ", availableModes)}");
Console.WriteLine($"Current mode: {await modeProvider.GetModeAsync(session)}");
PrintHelp(availableModes);
Console.WriteLine();

while (true)
{
    Console.Write("> ");
    string? input = Console.ReadLine()?.Trim();

    // Treat empty input or end-of-stream (Ctrl+D / Ctrl+Z) as a request to exit.
    if (string.IsNullOrWhiteSpace(input) || input.Equals("/exit", StringComparison.OrdinalIgnoreCase))
    {
        break;
    }

    if (input.Equals("/help", StringComparison.OrdinalIgnoreCase))
    {
        PrintHelp(availableModes);
        continue;
    }

    // Handle the /mode slash command: "/mode" shows the current mode, "/mode <name>" switches to it.
    if (input.Equals("/mode", StringComparison.OrdinalIgnoreCase) || input.StartsWith("/mode ", StringComparison.OrdinalIgnoreCase))
    {
        string[] parts = input.Split(' ', 2, StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries);
        if (parts.Length < 2)
        {
            Console.WriteLine($"Current mode: {await modeProvider.GetModeAsync(session)}");
            continue;
        }

        try
        {
            await modeProvider.SetModeAsync(session, parts[1]);
            Console.WriteLine($"Switched to \"{parts[1]}\" mode.");
        }
        catch (ArgumentException ex)
        {
            // SetModeAsync throws when the requested mode is not one of the configured modes.
            Console.WriteLine(ex.Message);
        }

        continue;
    }

    // Anything else is a message for the agent. The mode provider injects the current mode (and any
    // pending mode-change notification) into the context for this turn.
    Console.WriteLine(await agent.RunAsync(input, session));
}

static void PrintHelp(string[] availableModes)
{
    Console.WriteLine("Commands:");
    Console.WriteLine("  /mode            Show the current mode");
    Console.WriteLine($"  /mode <name>     Switch mode ({string.Join(" | ", availableModes)})");
    Console.WriteLine("  /help            Show this help");
    Console.WriteLine("  /exit            Quit");
}
