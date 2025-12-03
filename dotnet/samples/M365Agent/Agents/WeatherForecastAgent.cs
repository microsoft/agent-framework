// Copyright (c) Microsoft. All rights reserved.

using System.ComponentModel;
using System.Text.Json;
using AdaptiveCards;
using Microsoft.Agents.AI;
using Microsoft.Extensions.AI;

namespace M365Agent.Agents;

/// <summary>
/// A weather forecasting agent. This agent wraps a <see cref="ChatClientAgent"/> and adds custom logic
/// to generate adaptive cards for weather forecasts and add these to the agent's response.
/// </summary>
public class WeatherForecastAgent : DelegatingAIAgent
{
    private const string AgentName = "WeatherForecastAgent";
    private const string AgentInstructions = """
        You are a friendly assistant that helps people find a weather forecast for a given location.
        You may ask follow up questions until you have enough information to answer the customers question.
        When answering with a weather forecast, fill out the weatherCard property with an adaptive card containing the weather information and
        add some emojis to indicate the type of weather.
        When answering with just text, fill out the context property with a friendly response.
        """;

    /// <summary>
    /// Initializes a new instance of the <see cref="WeatherForecastAgent"/> class.
    /// </summary>
    /// <param name="chatClient">An instance of <see cref="IChatClient"/> for interacting with an LLM.</param>
    public WeatherForecastAgent(IChatClient chatClient)
        : base(new ChatClientAgent(
            chatClient: chatClient,
            new ChatClientAgentOptions()
            {
                Name = AgentName,
                ChatOptions = new ChatOptions()
                {
                    Instructions = AgentInstructions,
                    Tools = [new ApprovalRequiredAIFunction(AIFunctionFactory.Create(GetWeather))],
                    // We want the agent to return structured output in a known format
                    // so that we can easily create adaptive cards from the response.
                    ResponseFormat = ChatResponseFormat.ForJsonSchema(
                        schema: AIJsonUtilities.CreateJsonSchema(typeof(WeatherForecastAgentResponse)),
                        schemaName: "WeatherForecastAgentResponse",
                        schemaDescription: "Response to a query about the weather in a specified location"),
                }
            }))
    {
    }

    public override async Task<AgentRunResponse> RunAsync(IEnumerable<ChatMessage> messages, AgentThread? thread = null, AgentRunOptions? options = null, CancellationToken cancellationToken = default)
    {
        var response = await base.RunAsync(messages, thread, options, cancellationToken);

        // If the agent returned a valid structured output response
        // we might be able to enhance the response with an adaptive card.
        if (response.TryDeserialize<WeatherForecastAgentResponse>(JsonSerializerOptions.Web, out var structuredOutput))
        {
            var textContentMessage = response.Messages.FirstOrDefault(x => x.Contents.OfType<TextContent>().Any());
            if (textContentMessage is not null)
            {
                // If the response contains weather information, create an adaptive card.
                if (structuredOutput.ContentType == WeatherForecastAgentResponseContentType.WeatherForecastAgentResponse)
                {
                    var card = CreateWeatherCard(structuredOutput.Location, structuredOutput.MeteorologicalCondition, structuredOutput.TemperatureInCelsius);
                    textContentMessage.Contents.Add(new AdaptiveCardAIContent(card));
                }

                // If the response is just text, replace the structured output with the text response.
                if (structuredOutput.ContentType == WeatherForecastAgentResponseContentType.OtherAgentResponse)
                {
                    var textContent = textContentMessage.Contents.OfType<TextContent>().First();
                    textContent.Text = structuredOutput.OtherResponse;
                }
            }
        }

        return response;
    }

    /// <summary>
    /// A mock weather tool, to get weather information for a given location.
    /// </summary>
    [Description("Get the weather for a given location.")]
    private static string GetWeather([Description("The location to get the weather for.")] string location)
        => $"The weather in {location} is cloudy with a high of 15°C.";

    /// <summary>
    /// Create an adaptive card to display weather information.
    /// </summary>
    private static AdaptiveCard CreateWeatherCard(string? location, string? condition, string? temperature)
    {
        var card = new AdaptiveCard("1.5");
        card.Body.Add(new AdaptiveTextBlock
        {
            Text = "🌤️ Weather Forecast 🌤️",
            Size = AdaptiveTextSize.Large,
            Weight = AdaptiveTextWeight.Bolder,
            HorizontalAlignment = AdaptiveHorizontalAlignment.Center
        });
        card.Body.Add(new AdaptiveTextBlock
        {
            Text = "Location: " + location,
        });
        card.Body.Add(new AdaptiveTextBlock
        {
            Text = "Condition: " + condition,
        });
        card.Body.Add(new AdaptiveTextBlock
        {
            Text = "Temperature: " + temperature,
        });
        return card;
    }
}
