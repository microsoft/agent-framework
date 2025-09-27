// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.AI;
using Microsoft.Agents.Builder;
using Microsoft.Agents.Builder.App;
using Microsoft.Agents.Builder.State;
using Microsoft.Agents.Core.Models;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.DependencyInjection.Extensions;
using MultiTurn.Agents;

namespace MultiTurn;

public class MyAgent : AgentApplication
{
    private WeatherForecastAgent? _weatherAgent;
    private readonly IChatClient _chatClient;

    public MyAgent(AgentApplicationOptions options, IChatClient chatClient) : base(options)
    {
        this._chatClient = chatClient ?? throw new ArgumentNullException(nameof(chatClient));

        this.OnConversationUpdate(ConversationUpdateEvents.MembersAdded, this.WelcomeMessageAsync);

        this.OnActivity(ActivityTypes.Message, this.MessageActivityAsync, rank: RouteRank.Last);
    }

    protected async Task MessageActivityAsync(ITurnContext turnContext, ITurnState turnState, CancellationToken cancellationToken)
    {
        // Setup local service connection
        ServiceCollection serviceCollection = [
            new ServiceDescriptor(typeof(ITurnState), turnState),
            new ServiceDescriptor(typeof(ITurnContext), turnContext),
            new ServiceDescriptor(typeof(AIAgent), this._chatClient),
        ];

        // Start a Streaming Process 
        await turnContext.StreamingResponse.QueueInformativeUpdateAsync("Working on a response for you", cancellationToken);

        this._weatherAgent = new WeatherForecastAgent(this._chatClient, serviceCollection.BuildServiceProvider());
        AgentThread agentThread = turnState.GetValue("conversation.chatHistory", () => this._weatherAgent.GetNewThread());

        // Invoke the WeatherForecastAgent to process the message
        WeatherForecastAgentResponse forecastResponse = await this._weatherAgent.InvokeAgentAsync(turnContext.Activity.Text, agentThread);
        if (forecastResponse == null)
        {
            turnContext.StreamingResponse.QueueTextChunk("Sorry, I couldn't get the weather forecast at the moment.");
            await turnContext.StreamingResponse.EndStreamAsync(cancellationToken);
            return;
        }

        // Create a response message based on the response content type from the WeatherForecastAgent
        // Send the response message back to the user. 
        switch (forecastResponse.ContentType)
        {
            case WeatherForecastAgentResponseContentType.Text:
                turnContext.StreamingResponse.QueueTextChunk(forecastResponse.Content!);
                break;
            case WeatherForecastAgentResponseContentType.AdaptiveCard:
                turnContext.StreamingResponse.FinalMessage = MessageFactory.Attachment(new Attachment()
                {
                    ContentType = "application/vnd.microsoft.card.adaptive",
                    Content = forecastResponse.Content,
                });
                break;
            default:
                break;
        }
        await turnContext.StreamingResponse.EndStreamAsync(cancellationToken); // End the streaming response
    }

    protected async Task WelcomeMessageAsync(ITurnContext turnContext, ITurnState turnState, CancellationToken cancellationToken)
    {
        foreach (ChannelAccount member in turnContext.Activity.MembersAdded)
        {
            if (member.Id != turnContext.Activity.Recipient.Id)
            {
                await turnContext.SendActivityAsync(MessageFactory.Text("Hello and Welcome! I'm here to help with all your weather forecast needs!"), cancellationToken);
            }
        }
    }
}
