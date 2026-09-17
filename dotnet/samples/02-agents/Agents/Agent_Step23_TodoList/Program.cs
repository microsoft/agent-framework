// Copyright (c) Microsoft. All rights reserved.

// Todo List — Track work items across turns with TodoProvider
//
// This sample shows how to use the TodoProvider, an AIContextProvider that gives an agent a set of
// tools for managing a todo list (todos_add, todos_complete, todos_remove, todos_get_remaining,
// todos_get_all) along with instructions on how to use them. The todo list is stored in the
// session state and persists across turns, so the agent can plan multi-step work, track progress,
// and adjust the list as the conversation evolves.
//
// This is a scripted, non-interactive walkthrough: it sends a sequence of messages to the agent
// and, after each turn, prints the agent's reply followed by the current todo list (read directly
// from the provider via GetAllTodosAsync). This lets you watch the todo state evolve as the agent
// adds, completes, and removes items.

using Azure.AI.Projects;
using Azure.Identity;
using Microsoft.Agents.AI;
using Microsoft.Extensions.AI;

var endpoint = Environment.GetEnvironmentVariable("FOUNDRY_PROJECT_ENDPOINT") ?? throw new InvalidOperationException("FOUNDRY_PROJECT_ENDPOINT is not set.");
var model = Environment.GetEnvironmentVariable("FOUNDRY_MODEL") ?? "gpt-5.4-mini";

// <create_todo_provider>
// Create the TodoProvider and attach it to the agent as an AIContextProvider. The provider
// contributes the todo-management tools and instructions to every agent invocation.
using var todoProvider = new TodoProvider();

// WARNING: DefaultAzureCredential is convenient for development but requires careful consideration in production.
// In production, consider using a specific credential (e.g., ManagedIdentityCredential) to avoid
// latency issues, unintended credential probing, and potential security risks from fallback mechanisms.
AIAgent agent = new AIProjectClient(new Uri(endpoint), new DefaultAzureCredential())
    .AsAIAgent(new ChatClientAgentOptions
    {
        Name = "PlanningAssistant",
        ChatOptions = new ChatOptions
        {
            ModelId = model,
            Instructions = "You are a helpful planning assistant. Use your todo list to plan and track multi-step work.",
        },
        AIContextProviders = [todoProvider],
    });
// </create_todo_provider>

AgentSession session = await agent.CreateSessionAsync();

// A scripted set of turns that exercises the provider end-to-end: the agent should add todos for a
// multi-step request, mark items complete as progress is reported, and adjust the list on a change
// of plan.
string[] userMessages =
[
    "I'm organizing a small team offsite. Can you help me plan it? Break the work into a todo list.",
    "I've booked the venue and sent out the invites. Please update the list.",
    "Actually, let's skip catering and instead plan a group hike. Update the plan accordingly.",
];

foreach (string userMessage in userMessages)
{
    Console.WriteLine($"User: {userMessage}");
    Console.WriteLine($"Agent: {await agent.RunAsync(userMessage, session)}");

    // Read the current todo list straight from the provider and print it so the state is visible.
    await PrintTodoListAsync(todoProvider, session);
    Console.WriteLine();
}

static async Task PrintTodoListAsync(TodoProvider todoProvider, AgentSession session)
{
    IReadOnlyList<TodoItem> todos = await todoProvider.GetAllTodosAsync(session);

    Console.WriteLine("--- Current todo list ---");
    if (todos.Count == 0)
    {
        Console.WriteLine("  (empty)");
        return;
    }

    foreach (TodoItem todo in todos)
    {
        string status = todo.IsComplete ? "x" : " ";
        Console.WriteLine($"  [{status}] {todo.Id}. {todo.Title}");
    }
}
