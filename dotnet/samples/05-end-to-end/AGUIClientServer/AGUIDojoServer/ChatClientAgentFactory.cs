// Copyright (c) Microsoft. All rights reserved.

using System.ClientModel.Primitives;
using System.ComponentModel;
using System.Text.Json;
using AGUIDojoServer.AgenticUI;
using AGUIDojoServer.BackendToolRendering;
using AGUIDojoServer.PredictiveStateUpdates;
using AGUIDojoServer.SharedState;
using Azure.Identity;
using Microsoft.Agents.AI;
using Microsoft.Extensions.AI;
using OpenAI;
using OpenAI.Chat;

namespace AGUIDojoServer;

internal static class ChatClientAgentFactory
{
    private static OpenAIClient? s_azureOpenAIClient;
    private static string? s_deploymentName;

    public static void Initialize(IConfiguration configuration)
    {
        Uri endpoint = AzureOpenAIEndpoint.From(
            configuration["AZURE_OPENAI_ENDPOINT"])
            ?? throw new InvalidOperationException("AZURE_OPENAI_ENDPOINT is not set.");
        s_deploymentName = configuration["AZURE_OPENAI_DEPLOYMENT_NAME"] ?? throw new InvalidOperationException("AZURE_OPENAI_DEPLOYMENT_NAME is not set.");

        // WARNING: DefaultAzureCredential is convenient for development but requires careful consideration in production.
        // In production, consider using a specific credential (e.g., ManagedIdentityCredential) to avoid
        // latency issues, unintended credential probing, and potential security risks from fallback mechanisms.
        s_azureOpenAIClient = new OpenAIClient(
            new BearerTokenPolicy(new DefaultAzureCredential(), "https://ai.azure.com/.default"),
            new OpenAIClientOptions { Endpoint = endpoint });
    }

    public static ChatClientAgent CreateAgenticChat()
    {
        ChatClient chatClient = s_azureOpenAIClient!.GetChatClient(s_deploymentName!);

        return chatClient.AsAIAgent(
            name: "AgenticChat",
            description: "A simple chat agent using Azure OpenAI");
    }

    public static ChatClientAgent CreateBackendToolRendering()
    {
        ChatClient chatClient = s_azureOpenAIClient!.GetChatClient(s_deploymentName!);

        return chatClient.AsAIAgent(
            name: "BackendToolRenderer",
            description: "An agent that can render backend tools using Azure OpenAI",
            tools: [AIFunctionFactory.Create(
                GetWeather,
                name: "get_weather",
                description: "Get the weather for a given location.",
                AGUIDojoServerSerializerContext.Default.Options)]);
    }

    public static ChatClientAgent CreateHumanInTheLoop()
    {
        ChatClient chatClient = s_azureOpenAIClient!.GetChatClient(s_deploymentName!);

        return chatClient.AsAIAgent(
            name: "HumanInTheLoopAgent",
            description: "An agent that involves human feedback in its decision-making process using Azure OpenAI");
    }

    public static ChatClientAgent CreateToolBasedGenerativeUI()
    {
        ChatClient chatClient = s_azureOpenAIClient!.GetChatClient(s_deploymentName!);

        return chatClient.AsAIAgent(
            name: "ToolBasedGenerativeUIAgent",
            description: "An agent that uses tools to generate user interfaces using Azure OpenAI");
    }

    public static AIAgent CreateAgenticUI(JsonSerializerOptions options)
    {
        ChatClient chatClient = s_azureOpenAIClient!.GetChatClient(s_deploymentName!);
        var baseAgent = chatClient.AsAIAgent(new ChatClientAgentOptions
        {
            Name = "AgenticUIAgent",
            Description = "An agent that generates agentic user interfaces using Azure OpenAI",
            ChatOptions = new ChatOptions
            {
                Instructions = """
                    When planning use tools only, without any other messages.
                    IMPORTANT:
                    - Use the `create_plan` tool to set the initial state of the steps
                    - Use the `update_plan_step` tool to update the status of each step
                    - Do NOT repeat the plan or summarise it in a message
                    - Do NOT confirm the creation or updates in a message
                    - Do NOT ask the user for additional information or next steps
                    - Do NOT leave a plan hanging, always complete the plan via `update_plan_step` if one is ongoing.
                    - Continue calling update_plan_step until all steps are marked as completed.

                    Only one plan can be active at a time, so do not call the `create_plan` tool
                    again until all the steps in current plan are completed.
                    """,
                Tools = [
                    AIFunctionFactory.Create(
                        AgenticPlanningTools.CreatePlan,
                        name: "create_plan",
                        description: "Create a plan with multiple steps.",
                        AGUIDojoServerSerializerContext.Default.Options),
                    AIFunctionFactory.Create(
                        AgenticPlanningTools.UpdatePlanStepAsync,
                        name: "update_plan_step",
                        description: "Update a step in the plan with new description or status.",
                        AGUIDojoServerSerializerContext.Default.Options)
                ],
                AllowMultipleToolCalls = false
            }
        });

        return new AgenticUIAgent(baseAgent, options);
    }

    public static AIAgent CreateSharedState(JsonSerializerOptions options)
    {
        ChatClient chatClient = s_azureOpenAIClient!.GetChatClient(s_deploymentName!);

        var baseAgent = chatClient.AsAIAgent(
            name: "SharedStateAgent",
            description: "An agent that demonstrates shared state patterns using Azure OpenAI");

        return new SharedStateAgent(baseAgent, options);
    }

    public static AIAgent CreatePredictiveStateUpdates(JsonSerializerOptions options)
    {
        ChatClient chatClient = s_azureOpenAIClient!.GetChatClient(s_deploymentName!);

        var baseAgent = chatClient.AsAIAgent(new ChatClientAgentOptions
        {
            Name = "PredictiveStateUpdatesAgent",
            Description = "An agent that demonstrates predictive state updates using Azure OpenAI",
            // write_document runs on the server without approval, while confirm_changes runs on the client.
            // If the model requests both in one response, the function-invocation loop returns both calls
            // unexecuted because confirm_changes is only a declaration on the server. Bypassing saves
            // write_document in the server session and initially exposes only confirm_changes.
            // The client executes confirm_changes and sends its result with the original call ID in
            // a continuation request for the same thread. On that next request, the server executes
            // the saved write_document call. Its call and matching result then reach the client in
            // the continuation stream as completed history, not as a request for client-side execution.
            // Program.cs registers a session store keyed by this agent's name so the deferred call
            // survives across HTTP requests; without it, the call is lost when the client continues.
            // Execution therefore uses the stored call, not a call reconstructed from client-supplied history.
            EnableInvocableFunctionBypassing = true,
            ChatOptions = new ChatOptions
            {
                Instructions = """
                    You are a document editor assistant. When asked to write or edit content:
                    
                    IMPORTANT:
                    - Use the `write_document` tool with the full document text in Markdown format
                    - Format the document extensively so it's easy to read
                    - You can use all kinds of markdown (headings, lists, bold, etc.)
                    - However, do NOT use italic or strike-through formatting
                    - You MUST write the full document, even when changing only a few words
                    - When making edits to the document, try to make them minimal - do not change every word
                    - Keep stories SHORT!
                    - After you are done writing the document you MUST call a confirm_changes tool after you call write_document
                    
                    After the user confirms the changes, provide a brief summary of what you wrote.
                    """,
                Tools = [
                    AIFunctionFactory.Create(
                        WriteDocument,
                        name: "write_document",
                        description: "Write a document. Use markdown formatting to format the document.",
                        AGUIDojoServerSerializerContext.Default.Options)
                ]
            }
        });

        return new PredictiveStateUpdatesAgent(baseAgent, options);
    }

    [Description("Get the weather for a given location.")]
    private static WeatherInfo GetWeather([Description("The location to get the weather for.")] string location) => new()
    {
        Temperature = 20,
        Conditions = "sunny",
        Humidity = 50,
        WindSpeed = 10,
        FeelsLike = 25
    };

    [Description("Write a document in markdown format.")]
    private static string WriteDocument([Description("The document content to write.")] string document)
    {
        // Simply return success - the document is tracked via state updates
        return "Document written successfully";
    }
}
