// Copyright (c) Microsoft. All rights reserved.

using System.ComponentModel;
using System.Text.Json;
using AGUIDojoServer.A2UI;
using AGUIDojoServer.AgenticUI;
using AGUIDojoServer.BackendToolRendering;
using AGUIDojoServer.PredictiveStateUpdates;
using AGUIDojoServer.SharedState;
using Azure.AI.OpenAI;
using Azure.Identity;
using Microsoft.Agents.AI;
using Microsoft.Agents.AI.AGUI.A2UI;
using Microsoft.Extensions.AI;
using OpenAI;
using OpenAI.Chat;

namespace AGUIDojoServer;

internal static class ChatClientAgentFactory
{
    private static OpenAIClient? s_openAIClient;
    private static string? s_deploymentName;

    public static void Initialize(IConfiguration configuration)
    {
        string? azureEndpoint = configuration["AZURE_OPENAI_ENDPOINT"];
        if (!string.IsNullOrEmpty(azureEndpoint))
        {
            s_deploymentName = configuration["AZURE_OPENAI_DEPLOYMENT_NAME"] ?? throw new InvalidOperationException("AZURE_OPENAI_DEPLOYMENT_NAME is not set.");

            // WARNING: DefaultAzureCredential is convenient for development but requires careful consideration in production.
            // In production, consider using a specific credential (e.g., ManagedIdentityCredential) to avoid
            // latency issues, unintended credential probing, and potential security risks from fallback mechanisms.
            if (!Uri.TryCreate(azureEndpoint, UriKind.Absolute, out Uri? azureUri))
            {
                throw new InvalidOperationException($"AZURE_OPENAI_ENDPOINT is not a valid absolute URI: '{azureEndpoint}'.");
            }

            s_openAIClient = new AzureOpenAIClient(
                azureUri,
                new DefaultAzureCredential());
            return;
        }

        // OpenAI-compatible mode: OPENAI_API_KEY with an optional OPENAI_BASE_URL override
        // (e.g. a local mock server for deterministic end-to-end tests).
        string apiKey = configuration["OPENAI_API_KEY"] ?? throw new InvalidOperationException("Either AZURE_OPENAI_ENDPOINT or OPENAI_API_KEY must be set.");
        s_deploymentName = configuration["OPENAI_CHAT_MODEL_ID"] ?? "gpt-4o";

        var options = new OpenAIClientOptions();
        string? baseUrl = configuration["OPENAI_BASE_URL"];
        if (!string.IsNullOrEmpty(baseUrl))
        {
            if (!Uri.TryCreate(baseUrl, UriKind.Absolute, out Uri? baseUri))
            {
                throw new InvalidOperationException($"OPENAI_BASE_URL is not a valid absolute URI: '{baseUrl}'. Include the scheme, e.g. 'http://localhost:8000/v1'.");
            }

            options.Endpoint = baseUri;
        }

        s_openAIClient = new OpenAIClient(new System.ClientModel.ApiKeyCredential(apiKey), options);
    }

    public static ChatClientAgent CreateAgenticChat()
    {
        ChatClient chatClient = s_openAIClient!.GetChatClient(s_deploymentName!);

        return chatClient.AsAIAgent(
            name: "AgenticChat",
            description: "A simple chat agent");
    }

    public static ChatClientAgent CreateBackendToolRendering()
    {
        ChatClient chatClient = s_openAIClient!.GetChatClient(s_deploymentName!);

        return chatClient.AsAIAgent(
            name: "BackendToolRenderer",
            description: "An agent that can render backend tools",
            tools: [AIFunctionFactory.Create(
                GetWeather,
                name: "get_weather",
                description: "Get the weather for a given location.",
                AGUIDojoServerSerializerContext.Default.Options)]);
    }

    public static ChatClientAgent CreateHumanInTheLoop()
    {
        ChatClient chatClient = s_openAIClient!.GetChatClient(s_deploymentName!);

        return chatClient.AsAIAgent(
            name: "HumanInTheLoopAgent",
            description: "An agent that involves human feedback in its decision-making process");
    }

    public static ChatClientAgent CreateToolBasedGenerativeUI()
    {
        ChatClient chatClient = s_openAIClient!.GetChatClient(s_deploymentName!);

        return chatClient.AsAIAgent(
            name: "ToolBasedGenerativeUIAgent",
            description: "An agent that uses tools to generate user interfaces");
    }

    public static AIAgent CreateAgenticUI(JsonSerializerOptions options)
    {
        ChatClient chatClient = s_openAIClient!.GetChatClient(s_deploymentName!);
        var baseAgent = chatClient.AsAIAgent(new ChatClientAgentOptions
        {
            Name = "AgenticUIAgent",
            Description = "An agent that generates agentic user interfaces",
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
        ChatClient chatClient = s_openAIClient!.GetChatClient(s_deploymentName!);

        var baseAgent = chatClient.AsAIAgent(
            name: "SharedStateAgent",
            description: "An agent that demonstrates shared state patterns");

        return new SharedStateAgent(baseAgent, options);
    }

    public static AIAgent CreatePredictiveStateUpdates(JsonSerializerOptions options)
    {
        ChatClient chatClient = s_openAIClient!.GetChatClient(s_deploymentName!);

        var baseAgent = chatClient.AsAIAgent(new ChatClientAgentOptions
        {
            Name = "PredictiveStateUpdatesAgent",
            Description = "An agent that demonstrates predictive state updates",
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

    public static ChatClientAgent CreateA2UIFixedSchema()
    {
        ChatClient chatClient = s_openAIClient!.GetChatClient(s_deploymentName!);

        return chatClient.AsAIAgent(
            instructions: """
                You are a helpful travel assistant that can search for flights and hotels.

                When the user asks about flights, use the search_flights tool.
                When the user asks about hotels, use the search_hotels tool.
                IMPORTANT: After calling a tool, do NOT repeat or summarize the data in your text response. The tool renders a rich UI automatically. Just say something brief like "Here are your results" or ask if they'd like to book.
                """,
            name: "A2UIFixedSchema",
            description: "Fixed-schema A2UI demo: author-owned card layouts, agent-supplied data",
            tools: [A2UIFixedSchemaTools.CreateSearchFlightsTool(), A2UIFixedSchemaTools.CreateSearchHotelsTool()]);
    }

    public static AIAgent CreateA2UIDynamicSchema()
    {
        ChatClient chatClient = s_openAIClient!.GetChatClient(s_deploymentName!);

        AIAgent planner = chatClient.AsAIAgent(
            instructions: A2UICompositionGuides.PlannerInstructions,
            name: "A2UIDynamicSchema",
            description: "Dynamic-schema A2UI demo: a subagent designs the UI via generate_a2ui");

        return new A2UIAgent(planner, chatClient.AsIChatClient(), new A2UIToolParams
        {
            DefaultCatalogId = A2UICompositionGuides.DynamicCatalogId,
            Guidelines = new A2UIGuidelines { CompositionGuide = A2UICompositionGuides.DynamicSchema },
        });
    }

    public static AIAgent CreateA2UIChat()
    {
        ChatClient chatClient = s_openAIClient!.GetChatClient(s_deploymentName!);

        // Zero-configuration A2UI: the AG-UI A2UI middleware injects the render_a2ui
        // tool (auto-bound from the incoming tool list) plus its usage guidelines and
        // component schema as context entries. AGUIContextAgent surfaces those entries
        // to the model, so a plain chat agent renders A2UI surfaces with streamed,
        // progressively painted tool arguments — no A2UI-specific agent code.
        AIAgent inner = chatClient.AsAIAgent(
            instructions: "You are a helpful assistant. When the user asks for visual content (cards, lists, comparisons, dashboards), render it with the available UI rendering tool.",
            name: "A2UIChat",
            description: "Zero-configuration A2UI chat demo: client-injected render tool with streamed arguments");

        return new AGUIContextAgent(inner);
    }

    public static AIAgent CreateA2UIRecovery()
    {
        ChatClient chatClient = s_openAIClient!.GetChatClient(s_deploymentName!);

        AIAgent planner = chatClient.AsAIAgent(
            instructions: A2UICompositionGuides.PlannerInstructions,
            name: "A2UIRecovery",
            description: "A2UI error-recovery demo: invalid surfaces are validated and regenerated");

        return new A2UIAgent(planner, chatClient.AsIChatClient(), new A2UIToolParams
        {
            DefaultCatalogId = A2UICompositionGuides.DynamicCatalogId,
            Guidelines = new A2UIGuidelines { CompositionGuide = A2UICompositionGuides.Recovery },
            // No Catalog is supplied, so the loop exercises structural validation (missing
            // root, dangling child references, duplicate ids) like the sibling demos. The
            // recovery loop runs by default; the cap is set explicitly to show where the
            // knob lives, using the default value.
            Recovery = new A2UIRecoveryConfig { MaxAttempts = A2UIConstants.MaxA2UIAttempts },
        });
    }
}
