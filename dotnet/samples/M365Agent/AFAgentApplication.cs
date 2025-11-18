// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json;
using AdaptiveCards;
using M365Agent.Agents;
using Microsoft.Agents.AI;
using Microsoft.Agents.Builder;
using Microsoft.Agents.Builder.App;
using Microsoft.Agents.Builder.State;
using Microsoft.Agents.Core.Models;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.DependencyInjection;

namespace M365Agent;

/// <summary>
/// An adapter class that exposes a Microsoft Agent Framework <see cref="AIAgent"/> as a M365 Agent SDK <see cref="AgentApplication"/>.
/// </summary>
internal sealed class AFAgentApplication : AgentApplication
{
    private readonly AIAgent _agent;
    private readonly string? _welcomeMessage;

    public AFAgentApplication(AIAgent agent, AgentApplicationOptions options, [FromKeyedServices("AFAgentApplicationWelcomeMessage")] string? welcomeMessage = null) : base(options)
    {
        this._agent = agent;
        this._welcomeMessage = welcomeMessage;

        this.OnConversationUpdate(ConversationUpdateEvents.MembersAdded, this.WelcomeMessageAsync);
        this.OnActivity(ActivityTypes.Message, this.MessageActivityAsync, rank: RouteRank.Last);
    }

    /// <summary>
    /// The main agent invocation method, where each user message triggers a call to the underlying <see cref="AIAgent"/>.
    /// </summary>
    private async Task MessageActivityAsync(ITurnContext turnContext, ITurnState turnState, CancellationToken cancellationToken)
    {
        // Start a Streaming Process 
        await turnContext.StreamingResponse.QueueInformativeUpdateAsync("Working on a response for you", cancellationToken);

        // Get the conversation history from turn state.
        JsonElement threadElementStart = turnState.GetValue<JsonElement>("conversation.chatHistory");

        // Deserialize the conversation history into an AgentThread, or create a new one if none exists.
        AgentThread agentThread = threadElementStart.ValueKind is not JsonValueKind.Undefined and not JsonValueKind.Null
            ? this._agent.DeserializeThread(threadElementStart, JsonUtilities.DefaultOptions)
            : this._agent.GetNewThread();

        ChatMessage chatMessage = HandleUserInput(turnContext);

        // Invoke the WeatherForecastAgent to process the message
        AgentRunResponse agentRunResponse = await this._agent.RunAsync(chatMessage, agentThread, cancellationToken: cancellationToken);

        // Check for any user input requests in the response
        // and turn them into adaptive cards in the streaming response.
        List<Attachment>? attachments = null;
        HandleUserInputRequests(agentRunResponse, ref attachments);

        // Check for Adaptive Card content in the response messages
        // and return them appropriately in the response.
        var adaptiveCards = agentRunResponse.Messages.SelectMany(x => x.Contents).OfType<AdaptiveCardAIContent>().ToList();
        if (adaptiveCards.Count > 0)
        {
            attachments ??= [];
            attachments.Add(new Attachment()
            {
                ContentType = "application/vnd.microsoft.card.adaptive",
                Content = adaptiveCards.First().AdaptiveCardJson,
            });
        }
        else
        {
            turnContext.StreamingResponse.QueueTextChunk(agentRunResponse.Text);
        }

        // If created any adaptive cards, add them to the final message.
        if (attachments is not null)
        {
            turnContext.StreamingResponse.FinalMessage = MessageFactory.Attachment(attachments);
        }

        // Serialize and save the updated conversation history back to turn state.
        JsonElement threadElementEnd = agentThread.Serialize(JsonUtilities.DefaultOptions);
        turnState.SetValue("conversation.chatHistory", threadElementEnd);

        // End the streaming response
        await turnContext.StreamingResponse.EndStreamAsync(cancellationToken);
    }

    /// <summary>
    /// A method to show a welcome message when a new user joins the conversation.
    /// </summary>
    private async Task WelcomeMessageAsync(ITurnContext turnContext, ITurnState turnState, CancellationToken cancellationToken)
    {
        if (string.IsNullOrWhiteSpace(this._welcomeMessage))
        {
            return;
        }

        foreach (ChannelAccount member in turnContext.Activity.MembersAdded)
        {
            if (member.Id != turnContext.Activity.Recipient.Id)
            {
                await turnContext.SendActivityAsync(MessageFactory.Text(this._welcomeMessage), cancellationToken);
            }
        }
    }

    /// <summary>
    /// When a user responds to a function approval request by clicking on a card, this method converts the response
    /// into the appropriate approval or rejection <see cref="ChatMessage"/>.
    /// </summary>
    /// <param name="turnContext">The <see cref="ITurnContext"/> for the current turn.</param>
    /// <returns>The <see cref="ChatMessage"/> to pass to the <see cref="AIAgent"/>.</returns>
    private static ChatMessage HandleUserInput(ITurnContext turnContext)
    {
        // Check if this contains the function approval Adaptive Card response.
        if (turnContext.Activity.Value is JsonElement valueElement
            && valueElement.GetProperty("type").GetString() == "functionApproval"
            && valueElement.GetProperty("approved") is JsonElement approvedJsonElement
            && approvedJsonElement.ValueKind is JsonValueKind.True or JsonValueKind.False
            && valueElement.GetProperty("requestJson") is JsonElement requestJsonElement
            && requestJsonElement.ValueKind == JsonValueKind.String)
        {
            var requestContent = JsonSerializer.Deserialize<FunctionApprovalRequestContent>(requestJsonElement.GetString()!, JsonUtilities.DefaultOptions);

            return new ChatMessage(ChatRole.User, [requestContent!.CreateResponse(approvedJsonElement.ValueKind == JsonValueKind.True)]);
        }

        return new ChatMessage(ChatRole.User, turnContext.Activity.Text);
    }

    /// <summary>
    /// When the agent returns any user input requests, this method converts them into adaptive cards that
    /// asks the user to approve or deny the requests.
    /// </summary>
    /// <param name="response">The <see cref="AgentRunResponse"/> that may contain the user input requests.</param>
    /// <param name="attachments">The list of <see cref="Attachment"/> to which the adaptive cards will be added.</param>
    private static void HandleUserInputRequests(AgentRunResponse response, ref List<Attachment>? attachments)
    {
        var userInputRequests = response.UserInputRequests.ToList();
        if (userInputRequests.Count > 0)
        {
            foreach (var functionApprovalRequest in userInputRequests.OfType<FunctionApprovalRequestContent>())
            {
                var functionApprovalRequestJson = JsonSerializer.Serialize(functionApprovalRequest, JsonUtilities.DefaultOptions);

                var card = new AdaptiveCard("1.5");
                card.Body.Add(new AdaptiveTextBlock
                {
                    Text = "Function Call Approval Required",
                    Size = AdaptiveTextSize.Large,
                    Weight = AdaptiveTextWeight.Bolder,
                    HorizontalAlignment = AdaptiveHorizontalAlignment.Center
                });
                card.Body.Add(new AdaptiveTextBlock
                {
                    Text = $"Function: {functionApprovalRequest.FunctionCall.Name}"
                });
                card.Body.Add(new AdaptiveActionSet()
                {
                    Actions =
                    [
                        new AdaptiveSubmitAction
                        {
                            Id = "Approve",
                            Title = "Approve",
                            Data = new { type = "functionApproval", approved = true, requestJson = functionApprovalRequestJson }
                        },
                        new AdaptiveSubmitAction
                        {
                            Id = "Deny",
                            Title = "Deny",
                            Data = new { type = "functionApproval", approved = false, requestJson = functionApprovalRequestJson }
                        }
                    ]
                });

                attachments ??= [];
                attachments.Add(new Attachment()
                {
                    ContentType = "application/vnd.microsoft.card.adaptive",
                    Content = card.ToJson(),
                });
            }
        }
    }
}
