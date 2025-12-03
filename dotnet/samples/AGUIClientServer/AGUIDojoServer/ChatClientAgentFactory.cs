// Copyright (c) Microsoft. All rights reserved.

using System.ComponentModel;
using System.Text.Json;
using Azure.AI.OpenAI;
using Azure.Identity;
using Microsoft.Agents.AI;
using Microsoft.Extensions.AI;
using ChatClient = OpenAI.Chat.ChatClient;

namespace AGUIDojoServer;

internal static class ChatClientAgentFactory
{
    private static AzureOpenAIClient? s_azureOpenAIClient;
    private static string? s_deploymentName;

    public static void Initialize(IConfiguration configuration)
    {
        string endpoint = configuration["AZURE_OPENAI_ENDPOINT"] ?? throw new InvalidOperationException("AZURE_OPENAI_ENDPOINT is not set.");
        s_deploymentName = configuration["AZURE_OPENAI_DEPLOYMENT_NAME"] ?? throw new InvalidOperationException("AZURE_OPENAI_DEPLOYMENT_NAME is not set.");

        s_azureOpenAIClient = new AzureOpenAIClient(
            new Uri(endpoint),
            new DefaultAzureCredential());
    }

    public static ChatClientAgent CreateAgenticChat()
    {
        ChatClient chatClient = s_azureOpenAIClient!.GetChatClient(s_deploymentName!);

        return chatClient.AsIChatClient().CreateAIAgent(
            name: "AgenticChat",
            description: "A simple chat agent using Azure OpenAI");
    }

    public static ChatClientAgent CreateBackendToolRendering()
    {
        ChatClient chatClient = s_azureOpenAIClient!.GetChatClient(s_deploymentName!);

        return chatClient.AsIChatClient().CreateAIAgent(
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

        return chatClient.AsIChatClient().CreateAIAgent(
            name: "HumanInTheLoopAgent",
            description: "An agent that involves human feedback in its decision-making process using Azure OpenAI");
    }

    public static ChatClientAgent CreateToolBasedGenerativeUI()
    {
        ChatClient chatClient = s_azureOpenAIClient!.GetChatClient(s_deploymentName!);

        return chatClient.AsIChatClient().CreateAIAgent(
            name: "ToolBasedGenerativeUIAgent",
            description: "An agent that uses tools to generate user interfaces using Azure OpenAI");
    }

    public static ChatClientAgent CreateAgenticUI()
    {
        ChatClient chatClient = s_azureOpenAIClient!.GetChatClient(s_deploymentName!);

        return chatClient.AsIChatClient().CreateAIAgent(
            name: "AgenticUIAgent",
            description: "An agent that generates agentic user interfaces using Azure OpenAI");
    }

    public static AIAgent CreateSharedState(JsonSerializerOptions options)
    {
        ChatClient chatClient = s_azureOpenAIClient!.GetChatClient(s_deploymentName!);

        var baseAgent = chatClient.AsIChatClient().CreateAIAgent(
            name: "SharedStateAgent",
            description: "An agent that demonstrates shared state patterns using Azure OpenAI");

        return new SharedStateAgent(baseAgent, options);
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
}
