// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.Threading.Tasks;
using Microsoft.Agents.AI;
using Microsoft.Extensions.AI;

namespace MultiTurn.Agents;

public class WeatherForecastAgent
{
    private readonly IChatClient _chatClient;
    private readonly AIAgent _agent;

    private const string AgentName = "WeatherForecastAgent";
    private const string AgentInstructions = """
        You are a friendly assistant that helps people find a weather forecast for a given location.
        You may ask follow up questions until you have enough information to answer the customers question.
        """;

    /// <summary>
    /// Initializes a new instance of the <see cref="WeatherForecastAgent"/> class.
    /// </summary>
    /// <param name="chatClient">An instance of <see cref="IChatClient"/> for interacting with an LLM.</param>
    /// <param name="service"></param>
    public WeatherForecastAgent(IChatClient chatClient, IServiceProvider service)
    {
        this._chatClient = chatClient;

        // Give the agent some tools to work with
        [Description("Get the weather for a given location.")]
        static string GetWeather([Description("The location to get the weather for.")] string location)
            => $"The weather in {location} is cloudy with a high of 15°C.";
        IList<AITool> tools = [AIFunctionFactory.Create(GetWeather)];

        // Define the agent
        this._agent = new ChatClientAgent(
            chatClient: this._chatClient,
            new ChatClientAgentOptions()
            {
                Name = AgentName,
                Instructions = AgentInstructions,
                ChatOptions = new ChatOptions()
                {
                    Tools = tools,
                    //ResponseFormat = ChatResponseFormat.ForJsonSchema(
                    //    schema: AIJsonUtilities.CreateJsonSchema(typeof(WeatherForecastAgentResponse)),
                    //    schemaName: "WeatherForecastAgentResponse",
                    //    schemaDescription: "Response to a query about the weather in a specified location"),
                }
            });
    }

    /// <summary>
    /// Invokes the agent with the given input and returns the response.
    /// </summary>
    /// <param name="input">A message to process.</param>
    /// <param name="agentThread"></param>
    /// <returns>An instance of <see cref="WeatherForecastAgentResponse"/></returns>
    public async Task<WeatherForecastAgentResponse> InvokeAgentAsync(string input, AgentThread agentThread)
    {
        ArgumentNullException.ThrowIfNull(agentThread);

        // Invoke the agent and get the response
        var response = await this._agent.RunAsync(input, thread: agentThread);

        return new WeatherForecastAgentResponse()
        {
            ContentType = WeatherForecastAgentResponseContentType.Text,
            Content = response.ToString() ?? string.Empty
        };
    }

    internal AgentThread GetNewThread()
    {
        return this._agent.GetNewThread();
    }
}
