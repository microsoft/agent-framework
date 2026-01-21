// Copyright (c) Microsoft. All rights reserved.

// This sample shows how to inject additional AI context into a ChatClientAgent using a custom AIContextProvider component that is attached to the agent.
// The sample also shows how to combine the results from multiple providers into a single class, in order to attach multiple of these to an agent.
// This mechanism can be used for various purposes, such as injecting RAG search results or memories into the agent's context.
// Also note that Agent Framework already provides built-in AIContextProviders for many of these scenarios.

#pragma warning disable CA1869 // Cache and reuse 'JsonSerializerOptions' instances

using System.ComponentModel;
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
AIAgent agent = new AzureOpenAIClient(
    new Uri(endpoint),
    new AzureCliCredential())
    .GetChatClient(deploymentName)
    .AsAIAgent(new ChatClientAgentOptions()
    {
        ChatOptions = new() { Instructions = """
        You are a helpful personal assistant.
        You manage a TODO list for the user. When the user has completed one of the tasks it can be removed from the TODO list. Only provide the list of TODO items if asked.
        You remind users of upcoming calendar events when the user interacts with you.
        """ },
        ChatMessageStoreFactory = (ctx, ct) => new ValueTask<ChatMessageStore>(new InMemoryChatMessageStore()
            // Use WithAIContextProviderMessageRemoval, so that we don't store the messages from the AI context provider in the chat history.
            // You may want to store these messages, depending on their content and your requirements.
            .WithAIContextProviderMessageRemoval()),
        // Add an AI context provider that maintains a todo list for the agent and one that provides upcoming calendar entries.
        // Wrap these in an AI context provider that aggregates the other two.
        AIContextProviderFactory = (ctx, ct) => new ValueTask<AIContextProvider>(new AggregatingAIContextProvider([
            AggregatingAIContextProvider.CreateFactory((jsonElement, jsonSerializerOptions) => new TodoListAIContextProvider(jsonElement, jsonSerializerOptions)),
            AggregatingAIContextProvider.CreateFactory((_, _) => new CalendarSearchAIContextProvider(loadNextThreeCalendarEvents))
        ], ctx.SerializedState, ctx.JsonSerializerOptions)),
    });

// Invoke the agent and output the text result.
AgentThread thread = await agent.GetNewThreadAsync();
Console.WriteLine(await agent.RunAsync("I need to pick up milk from the supermarket.", thread) + "\n");
Console.WriteLine(await agent.RunAsync("I need to take Sally for soccer practice.", thread) + "\n");
Console.WriteLine(await agent.RunAsync("I need to make a dentist appointment for Jimmy.", thread) + "\n");
Console.WriteLine(await agent.RunAsync("I've taken Sally to soccer practice.", thread) + "\n");

// We can serialize the thread, and it will contain both the chat history and the data that each AI context provider serialized.
JsonElement serializedThread = thread.Serialize();
// Let's print it to console to show the contents.
Console.WriteLine(JsonSerializer.Serialize(serializedThread, options: new JsonSerializerOptions() { WriteIndented = true, IndentSize = 2 }) + "\n");
// The serialized thread can be stored long term in a persistent store, but in this case we will just deserialize again and continue the conversation.
thread = await agent.DeserializeThreadAsync(serializedThread);

Console.WriteLine(await agent.RunAsync("Considering my appointments, can you create a plan for my day that plans out when I should complete the items on my todo list?", thread) + "\n");

namespace SampleApp
{
    /// <summary>
    /// An <see cref="AIContextProvider"/>, which maintains a todo list for the agent.
    /// </summary>
    internal sealed class TodoListAIContextProvider : AIContextProvider
    {
        private readonly List<string> _todoItems = new();

        public TodoListAIContextProvider(JsonElement jsonElement, JsonSerializerOptions? jsonSerializerOptions = null)
        {
            // Only try and restore the state if we got an array, since any other json would be invalid or undefined/null meaning
            // it's the first time we are running.
            if (jsonElement.ValueKind == JsonValueKind.Array)
            {
                this._todoItems = JsonSerializer.Deserialize<List<string>>(jsonElement.GetRawText(), jsonSerializerOptions) ?? new List<string>();
            }
        }

        public override ValueTask<AIContext> InvokingAsync(InvokingContext context, CancellationToken cancellationToken = default)
        {
            StringBuilder outputMessageBuilder = new();
            outputMessageBuilder.AppendLine("Your todo list contains the following items:");

            if (this._todoItems.Count == 0)
            {
                outputMessageBuilder.AppendLine("  (no items)");
            }
            else
            {
                for (int i = 0; i < this._todoItems.Count; i++)
                {
                    outputMessageBuilder.AppendLine($"{i}. {this._todoItems[i]}");
                }
            }

            return new ValueTask<AIContext>(new AIContext
            {
                Tools = [AIFunctionFactory.Create(this.AddTodoItem), AIFunctionFactory.Create(this.RemoveTodoItem)],
                Messages = [new MEAI.ChatMessage(ChatRole.User, outputMessageBuilder.ToString())]
            });
        }

        [Description("Adds an item to the todo list. Index is zero based.")]
        private void RemoveTodoItem(int index) =>
            this._todoItems.RemoveAt(index);

        private void AddTodoItem(string item) =>
            this._todoItems.Add(string.IsNullOrWhiteSpace(item) ? throw new ArgumentException("Item must have a value") : item);

        public override JsonElement Serialize(JsonSerializerOptions? jsonSerializerOptions = null) =>
            JsonSerializer.SerializeToElement(this._todoItems, jsonSerializerOptions);
    }

    /// <summary>
    /// An <see cref="AIContextProvider"/> which searches for upcoming calendar events and adds them to the AI context.
    /// </summary>
    internal sealed class CalendarSearchAIContextProvider(Func<Task<string[]>> loadNextThreeCalendarEvents) : AIContextProvider
    {
        public override async ValueTask<AIContext> InvokingAsync(InvokingContext context, CancellationToken cancellationToken = default)
        {
            var events = await loadNextThreeCalendarEvents();

            StringBuilder outputMessageBuilder = new();
            outputMessageBuilder.AppendLine("You have the following upcoming calendar events:");
            foreach (var calendarEvent in events)
            {
                outputMessageBuilder.AppendLine($" - {calendarEvent}");
            }

            return new()
            {
                Messages =
                [
                    new MEAI.ChatMessage(ChatRole.User, outputMessageBuilder.ToString()),
                ]
            };
        }
    }

    /// <summary>
    /// An <see cref="AIContextProvider"/> which aggregates multiple AI context providers into one.
    /// Serialized state for the different providers are stored under their type name.
    /// Tools and messages from all providers are combined, and instructions are concatenated.
    /// </summary>
    internal sealed class AggregatingAIContextProvider : AIContextProvider
    {
        private readonly List<AIContextProvider> _providers = new();

        public AggregatingAIContextProvider(ProviderFactory[] providerFactories, JsonElement jsonElement, JsonSerializerOptions? jsonSerializerOptions)
        {
            // We received a json object, so let's check if it has some previously serialized state that we can use.
            if (jsonElement.ValueKind == JsonValueKind.Object)
            {
                this._providers = providerFactories
                    .Select(factory => factory.FactoryMethod(jsonElement.TryGetProperty(factory.ProviderType.Name, out var prop) ? prop : default, jsonSerializerOptions))
                    .ToList();
                return;
            }

            // We didn't receive any valid json, so we can just construct fresh providers.
            this._providers = providerFactories
                .Select(factory => factory.FactoryMethod(default, jsonSerializerOptions))
                .ToList();
        }

        public override async ValueTask<AIContext> InvokingAsync(InvokingContext context, CancellationToken cancellationToken = default)
        {
            // Invoke all the sub providers.
            var tasks = this._providers.Select(provider => provider.InvokingAsync(context, cancellationToken).AsTask());
            var results = await Task.WhenAll(tasks);

            // Combine the results from each sub provider.
            return new AIContext
            {
                Tools = results.SelectMany(r => r.Tools ?? []).ToList(),
                Messages = results.SelectMany(r => r.Messages ?? []).ToList(),
                Instructions = string.Join("\n", results.Select(r => r.Instructions).Where(s => !string.IsNullOrEmpty(s)))
            };
        }

        public override JsonElement Serialize(JsonSerializerOptions? jsonSerializerOptions = null)
        {
            Dictionary<string, JsonElement> elements = new();
            foreach (var provider in this._providers)
            {
                JsonElement element = provider.Serialize(jsonSerializerOptions);

                // Don't try to store state for any providers that aren't producing any.
                if (element.ValueKind != JsonValueKind.Undefined && element.ValueKind != JsonValueKind.Null)
                {
                    elements[provider.GetType().Name] = element;
                }
            }

            return JsonSerializer.SerializeToElement(elements, jsonSerializerOptions);
        }

        public static ProviderFactory CreateFactory<TProviderType>(Func<JsonElement, JsonSerializerOptions?, TProviderType> factoryMethod)
            where TProviderType : AIContextProvider => new()
            {
                FactoryMethod = (jsonElement, jsonSerializerOptions) => factoryMethod(jsonElement, jsonSerializerOptions),
                ProviderType = typeof(TProviderType)
            };

        public readonly struct ProviderFactory
        {
            public Func<JsonElement, JsonSerializerOptions?, AIContextProvider> FactoryMethod { get; init; }

            public Type ProviderType { get; init; }
        }
    }
}
