// Copyright (c) Microsoft. All rights reserved.

// This sample shows how to inject additional AI context into a ChatClientAgent using custom AIContextProvider components that are attached to the agent.
// Multiple providers can be attached to an agent, and they will be called in sequence, each receiving the accumulated context from the previous one.
// This mechanism can be used for various purposes, such as injecting RAG search results or memories into the agent's context.
// Also note that Agent Framework already provides built-in AIContextProviders for many of these scenarios.

#pragma warning disable CA1869 // Cache and reuse 'JsonSerializerOptions' instances

using System.Text;
using System.Text.Json;
using Azure.AI.OpenAI;
using Azure.Identity;
using Microsoft.Agents.AI;
using Microsoft.Extensions.AI;
using OpenAI.Chat;
using SampleApp;
using MEAI = Microsoft.Extensions.AI;

var endpoint = Environment.GetEnvironmentVariable("AZURE_OPENAI_ENDPOINT") ?? throw new InvalidOperationException("AZURE_OPENAI_ENDPOINT is not set.");
var deploymentName = Environment.GetEnvironmentVariable("AZURE_OPENAI_DEPLOYMENT_NAME") ?? "gpt-5-mini";

// A sample function to load the next three calendar events for the user.
Func<Task<string[]>> loadNextThreeCalendarEvents = async () =>
{
    // In a real implementation, this method would connect to a calendar service
    return new string[]
    {
        "Doctor's appointment today at 15:00",
        "Team meeting today at 17:00",
        "Birthday party today at 20:00"
    };
};

// Create an agent with an AI context provider attached that aggregates two other providers:
// WARNING: DefaultAzureCredential is convenient for development but requires careful consideration in production.
// In production, consider using a specific credential (e.g., ManagedIdentityCredential) to avoid
// latency issues, unintended credential probing, and potential security risks from fallback mechanisms.
AIAgent agent = new AzureOpenAIClient(
    new Uri(endpoint),
    new DefaultAzureCredential())
    .GetChatClient(deploymentName)
    .AsAIAgent(new ChatClientAgentOptions()
    {
        ChatOptions = new() { Instructions = """
        You are a helpful personal assistant.
        You manage a TODO list for the user. When the user has completed one of the tasks it can be removed from the TODO list. Only provide the list of TODO items if asked.
        You remind users of upcoming calendar events when the user interacts with you.
        """ },
        ChatHistoryProvider = new InMemoryChatHistoryProvider(new InMemoryChatHistoryProviderOptions
        {
            // Use StorageInputMessageFilter to provide a custom filter for messages stored in chat history.
            // By default the chat history provider will store all messages, except for those that came from chat history in the first place.
            // In this case, we want to also exclude messages that came from AI context providers.
            // You may want to store these messages, depending on their content and your requirements.
            StorageInputMessageFilter = messages => messages.Where(m => m.GetAgentRequestMessageSourceType() != AgentRequestMessageSourceType.AIContextProvider && m.GetAgentRequestMessageSourceType() != AgentRequestMessageSourceType.ChatHistory)
        }),
        // Add multiple AI context providers: one that maintains a todo list and one that provides upcoming calendar entries.
        // The agent will call each provider in sequence, accumulating context from each.
        AIContextProviders = [
            new TodoListAIContextProvider(),
            new CalendarSearchAIContextProvider(loadNextThreeCalendarEvents)
        ],
    });

// Invoke the agent and output the text result.
AgentSession session = await agent.CreateSessionAsync();
Console.WriteLine(await agent.RunAsync("I need to pick up milk from the supermarket.", session) + "\n");
Console.WriteLine(await agent.RunAsync("I need to take Sally for soccer practice.", session) + "\n");
Console.WriteLine(await agent.RunAsync("I need to make a dentist appointment for Jimmy.", session) + "\n");
Console.WriteLine(await agent.RunAsync("I've taken Sally to soccer practice.", session) + "\n");

// We can serialize the session, and it will contain both the chat history and the data that each AI context provider serialized.
JsonElement serializedSession = await agent.SerializeSessionAsync(session);
// Let's print it to console to show the contents.
Console.WriteLine(JsonSerializer.Serialize(serializedSession, options: new JsonSerializerOptions() { WriteIndented = true, IndentSize = 2 }) + "\n");
// The serialized session can be stored long term in a persistent store, but in this case we will just deserialize again and continue the conversation.
session = await agent.DeserializeSessionAsync(serializedSession);

Console.WriteLine(await agent.RunAsync("Considering my appointments, can you create a plan for my day that plans out when I should complete the items on my todo list?", session) + "\n");

namespace SampleApp
{
    /// <summary>
    /// An <see cref="AIContextProvider"/>, which maintains a todo list for the agent.
    /// </summary>
    internal sealed class TodoListAIContextProvider : AIContextProvider
    {
        private static List<string> GetTodoItems(AgentSession? session)
            => session?.StateBag.GetValue<List<string>>(nameof(TodoListAIContextProvider)) ?? new List<string>();

        private static void SetTodoItems(AgentSession? session, List<string> items)
            => session?.StateBag.SetValue(nameof(TodoListAIContextProvider), items);

        protected override ValueTask<AIContext> ProvideAIContextAsync(InvokingContext context, CancellationToken cancellationToken = default)
        {
            var todoItems = GetTodoItems(context.Session);

            StringBuilder outputMessageBuilder = new();
            outputMessageBuilder.AppendLine("Your todo list contains the following items:");

            if (todoItems.Count == 0)
            {
                outputMessageBuilder.AppendLine("  (no items)");
            }
            else
            {
                for (int i = 0; i < todoItems.Count; i++)
                {
                    outputMessageBuilder.AppendLine($"{i}. {todoItems[i]}");
                }
            }

            return new ValueTask<AIContext>(new AIContext
            {
                Tools =
                [
                    AIFunctionFactory.Create((string item) => AddTodoItem(context.Session, item), "AddTodoItem", "Adds an item to the todo list."),
                    AIFunctionFactory.Create((int index) => RemoveTodoItem(context.Session, index), "RemoveTodoItem", "Removes an item from the todo list. Index is zero based.")
                ],
                Messages =
                [
                    new MEAI.ChatMessage(ChatRole.User, outputMessageBuilder.ToString())
                ]
            });
        }

        private static void RemoveTodoItem(AgentSession? session, int index)
        {
            var items = GetTodoItems(session);
            items.RemoveAt(index);
            SetTodoItems(session, items);
        }

        private static void AddTodoItem(AgentSession? session, string item)
        {
            if (string.IsNullOrWhiteSpace(item))
            {
                throw new ArgumentException("Item must have a value");
            }

            var items = GetTodoItems(session);
            items.Add(item);
            SetTodoItems(session, items);
        }
    }

    /// <summary>
    /// A <see cref="MessageAIContextProvider"/> which searches for upcoming calendar events and adds them to the AI context.
    /// </summary>
    internal sealed class CalendarSearchAIContextProvider(Func<Task<string[]>> loadNextThreeCalendarEvents) : MessageAIContextProvider
    {
        protected override async ValueTask<IEnumerable<MEAI.ChatMessage>> ProvideMessagesAsync(InvokingContext context, CancellationToken cancellationToken = default)
        {
            var events = await loadNextThreeCalendarEvents();

            StringBuilder outputMessageBuilder = new();
            outputMessageBuilder.AppendLine("You have the following upcoming calendar events:");
            foreach (var calendarEvent in events)
            {
                outputMessageBuilder.AppendLine($" - {calendarEvent}");
            }

            return [new MEAI.ChatMessage(ChatRole.User, outputMessageBuilder.ToString())];
        }
    }
}
