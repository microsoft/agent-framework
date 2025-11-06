// Copyright (c) Microsoft. All rights reserved.

using System.ComponentModel;
using Azure.AI.OpenAI;
using Azure.Identity;
using Microsoft.Agents.AI;
using Microsoft.Extensions.AI;
using OpenAI;

namespace AGUIDojoServer;

public class ChatClientAgentFactory
{
    private readonly IConfiguration _configuration;
    private readonly AzureOpenAIClient _azureOpenAIClient;
    private readonly string _deploymentName;

    public ChatClientAgentFactory(IConfiguration configuration)
    {
        _configuration = configuration;

        string endpoint = _configuration["AZURE_OPENAI_ENDPOINT"] ?? throw new InvalidOperationException("AZURE_OPENAI_ENDPOINT is not set.");
        _deploymentName = _configuration["AZURE_OPENAI_DEPLOYMENT_NAME"] ?? throw new InvalidOperationException("AZURE_OPENAI_DEPLOYMENT_NAME is not set.");

        _azureOpenAIClient = new AzureOpenAIClient(
            new Uri(endpoint),
            new DefaultAzureCredential());
    }

    public ChatClientAgent CreateAgenticChat()
    {
        var chatClient = _azureOpenAIClient.GetChatClient(_deploymentName);

        return chatClient.CreateAIAgent(
            name: "AgenticChat",
            description: "A simple chat agent using Azure OpenAI");
    }

    public ChatClientAgent CreateBackendToolRendering()
    {
        var chatClient = _azureOpenAIClient.GetChatClient(_deploymentName);

        return chatClient.CreateAIAgent(
            name: "BackendToolRenderer",
            description: "An agent that can render backend tools using Azure OpenAI",
            tools: [AIFunctionFactory.Create(
                GetWeather,
                name: "get_weather",
                description: "Get the weather for a given location.",
                AGUIDojoServerSerializerContext.Default.Options)]);
    }

    public ChatClientAgent CreateHumanInTheLoop()
    {
        var chatClient = _azureOpenAIClient.GetChatClient(_deploymentName);

        return chatClient.CreateAIAgent(
            name: "HumanInTheLoopAgent",
            description: "An agent that involves human feedback in its decision-making process using Azure OpenAI");
    }

    public ChatClientAgent CreateToolBasedGenerativeUI()
    {
        var chatClient = _azureOpenAIClient.GetChatClient(_deploymentName);

        return chatClient.CreateAIAgent(
            name: "ToolBasedGenerativeUIAgent",
            description: "An agent that uses tools to generate user interfaces using Azure OpenAI");
    }

    public ChatClientAgent CreateAgenticUI()
    {
        var chatClient = _azureOpenAIClient.GetChatClient(_deploymentName);

        return chatClient.CreateAIAgent(
            name: "AgenticUIAgent",
            description: "An agent that generates agentic user interfaces using Azure OpenAI");
    }

    public ChatClientAgent CreateSharedState()
    {
        var chatClient = _azureOpenAIClient.GetChatClient(_deploymentName);

        return chatClient.CreateAIAgent(
            name: "SharedStateAgent",
            description: "An agent that demonstrates shared state patterns using Azure OpenAI");
    }

    [Description("Get the weather for a given location.")]
    private static WeatherInfo GetWeather([Description("The location to get the weather for.")] string location) => new WeatherInfo
    {
        Temperature = 20,
        Conditions = "sunny",
        Humidity = 50,
        WindSpeed = 10,
        FeelsLike = 25
    };
}
