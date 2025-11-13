// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.AI.AGUI;
using Microsoft.Extensions.AI;

namespace AGUIDojoClient.Components.Shared;

/// <summary>
/// Service for managing demo scenarios and creating chat clients for each scenario.
/// </summary>
public sealed class DemoService
{
    private readonly IHttpClientFactory _httpClientFactory;
    private readonly List<DemoScenario> _scenarios;

    /// <summary>
    /// Initializes a new instance of the <see cref="DemoService"/> class.
    /// </summary>
    /// <param name="httpClientFactory">Factory for creating HTTP clients.</param>
    public DemoService(IHttpClientFactory httpClientFactory)
    {
        _httpClientFactory = httpClientFactory;
        _scenarios = InitializeScenarios();
    }

    /// <summary>
    /// Gets all available demo scenarios.
    /// </summary>
    public IEnumerable<DemoScenario> AllScenarios => this._scenarios;

    /// <summary>
    /// Gets a specific scenario by its ID.
    /// </summary>
    /// <param name="id">The scenario identifier.</param>
    /// <returns>The scenario if found; otherwise, null.</returns>
    public DemoScenario? GetScenario(string id)
        => this._scenarios.FirstOrDefault(s => s.Id.Equals(id, StringComparison.OrdinalIgnoreCase));

    /// <summary>
    /// Creates a chat client for the specified endpoint.
    /// </summary>
    /// <param name="endpoint">The AG-UI endpoint path.</param>
    /// <returns>A configured chat client.</returns>
    public IChatClient CreateChatClient(string endpoint)
    {
        HttpClient httpClient = this._httpClientFactory.CreateClient("aguiserver");
        return new AGUIChatClient(httpClient, endpoint);
    }

    private static List<DemoScenario> InitializeScenarios()
    {
        return
        [
            new DemoScenario(
                Id: "agentic_chat",
                Title: "Agentic Chat",
                Description: "Chat with your Copilot and call frontend tools",
                Tags: ["Chat", "Tools", "Streaming"],
                Endpoint: "/agentic_chat",
                Icon: "💬"
            ),
            new DemoScenario(
                Id: "backend_tool_rendering",
                Title: "Backend Tool Rendering",
                Description: "Render and stream your backend tools to the frontend",
                Tags: ["Agent State", "Collaborating"],
                Endpoint: "/backend_tool_rendering",
                Icon: "🛠️"
            ),
            new DemoScenario(
                Id: "human_in_the_loop",
                Title: "Human in the Loop",
                Description: "Plan a task together and direct the Copilot to take the right steps",
                Tags: ["HITL", "Interactivity"],
                Endpoint: "/human_in_the_loop",
                Icon: "👤"
            ),
            new DemoScenario(
                Id: "agentic_generative_ui",
                Title: "Agentic Generative UI",
                Description: "Assign a long running task to your Copilot and see how it performs!",
                Tags: ["Generative UI (agent)", "Long running task"],
                Endpoint: "/agentic_generative_ui",
                Icon: "🤖"
            ),
            new DemoScenario(
                Id: "tool_based_generative_ui",
                Title: "Tool Based Generative UI",
                Description: "Haiku generator that uses tool based generative UI",
                Tags: ["Generative UI (action)", "Tools"],
                Endpoint: "/tool_based_generative_ui",
                Icon: "🎨"
            ),
            new DemoScenario(
                Id: "shared_state",
                Title: "Shared State between Agent and UI",
                Description: "A recipe Copilot which reads and updates collaboratively",
                Tags: ["Agent State", "Collaborating"],
                Endpoint: "/shared_state",
                Icon: "🍳"
            ),
            new DemoScenario(
                Id: "predictive_state_updates",
                Title: "Predictive State Updates",
                Description: "Use collaboration to edit a document in real time with your Copilot",
                Tags: ["State", "Streaming", "Tools"],
                Endpoint: "/predictive_state_updates",
                Icon: "📝"
            )
        ];
    }
}
