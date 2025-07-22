---
# These are optional elements. Feel free to remove any of them.
status: proposed
contact: westey-m
date: 2025-07-16 {YYYY-MM-DD when the decision was last updated}
deciders: sergeymenshykh, markwallace, rbarreto, dmytrostruk, westey-m, eavanvalkenburg, stephentoub
consulted: 
informed: 
---

# Agent User Approvals Content Types Design

## Context and Problem Statement

When agents are operating on behalf of a user, there may be cases where the agent requires user approval to continue an operation.
This is complicated by the fact that an agent may be remote and the user may not immediately be available to provide the approval.

Inference services are also increasingly supporting built-in tools or service side MCP invocation, which may require user approval before the tool can be invoked.

This document aims to provide options and capture the decision on how to model this user approval interaction with the agent caller.

## Decision Drivers

## Considered Options

### Return a FunctionCallContent to the agent caller, that it executes

This introduces a manual function calling element to agents, where the caller of the agent is expected to invoke the function if the user approves it.

This approach is problematic for a number of reasons:

- This may not work for remote agents (e.g. via A2A), where the function that the agent wants to call does not reside on the caller's machine.
- The main value prop of an agent is to encapsulate the internal logic of the agent, but this leaks that logic to the caller, requiring the caller to know how to invoke the agent's function calls.
- Inference services are introducing their own approval content types for server side tool or function invocation, and will not be addressed by this approach.

### Introduce new ApprovalRequestContent and ApprovalResponseContent types

The agent would return an `ApprovalRequestContent` to the caller, which would then be responsible for getting approval from the user in whatever way is appropriate for the application.
The caller would then invoke the agent again with an `ApprovalResponseContent` to the agent containing the user decision.

When an agent returns an `ApprovalRequestContent`, the run is finished for the time being, and to continue, the agent must be invoked again with an `ApprovalResponseContent` on the same thread as the original request.

The `ApprovalRequestContent` could contain an optional `FunctionCallContent` if the approval is for a function call, along with any additional information that the agent wants to provide to the user to help them make a decision.

It is up to the agent to decide when and if a user approval is required, and therefore when to return an `ApprovalRequestContent`.

`ApprovalRequestContent` and `ApprovalResponseContent` will not necessarily always map to a supported content type for the underlying service or agent thread storage.
Specifically, when we are deciding in the IChatClient stack to ask for approval from the user, for a function call, this does not mean that the underlying ai service or
service side thread type (where applicable) supports the concept of a function call approval request.  We therefore need the ability to temporarily store the approval request in the
AgentThread, without it becoming part of the thread history. This will serve as a temporary record of the fact that there is an outstanding approval request that the agent is waiting for to continue.
There will be no long term record of an approval request in the chat history, but if the server side thread doesn't support this, there is nothing we can do to change that.

Suggested Types:

```csharp
class ApprovalRequestContent : TextContent // TextContent.Text may contain text to explain to the user what they are approving. This is important if the approval is not for a function call.
{
    // An ID to uniquely identify the approval request/response pair.
    public string ApprovalId { get; set; }

    // Optional: If the approval is for a function call, this will contain the function call content.
    public FunctionCallContent? FunctionCall { get; set; }

    public ChatMessage Approve()
    {
        return new ChatMessage(ChatRole.User,
        [
            new ApprovalResponseContent
            {
                ApprovalId = this.ApprovalId,
                Approved = true,
                FunctionCall = this.FunctionCall
            }
        ]);
    }

    public ChatMessage Reject()
    {
        return new ChatMessage(ChatRole.User,
        [
            new ApprovalResponseContent
            {
                ApprovalId = this.ApprovalId,
                Approved = false,
                FunctionCall = this.FunctionCall
            }
        ]);
    }
}

class ApprovalResponseContent : AIContent
{
    // An ID to uniquely identify the approval request/response pair.
    public string ApprovalId { get; set; }

    // Indicates whether the user approved the request.
    public bool Approved { get; set; }

    // Optional: If the approval is for a function call, this will contain the function call content.
    public FunctionCallContent? FunctionCall { get; set; }
}

var response = await agent.RunAsync("Please book me a flight for Friday to Paris.", thread);
while (response is not null && response.ApprovalRequests.Count > 0)
{
    List<ChatMessage> messages = new List<ChatMessage>();
    foreach (var approvalRequest in response.ApprovalRequests)
    {
        // Show the approval request to the user in the appropriate format.
        // The user can then approve or reject the request.
        // The optional FunctionCallContent can be used to show the user what function the agent wants to call with the parameter set:
        // approvalRequest.FunctionCall?.Arguments.
        // The Text property of the ApprovalRequestContent can also be used to show the user any additional textual context about the request.
    
        // If the user approves:
        var approvalMessage = approvalRequest.Approve();
        messages.Add(approvalMessage);
    }

    // Get the next response from the agent.
    response = await agent.RunAsync(messages, thread);
}

class AgentThread
{
    ...

    // The thread state may need to store the approval requests and responses.
    // TODO: CConsider whether we should have a more generic ActiveUserRequests list, which could include other types of user requests in the future.
    // This may mean a base class for all user requests.
    public List<ApprovalRequestContent> ActiveApprovalRequests { get; set; }

    ...
}
```

- Also see [dotnet issue 6492](https://github.com/dotnet/extensions/issues/6492), which discusses the need for a similar pattern in the context of MCP approvals.
- Also see [the openai RunToolApprovalItem](https://openai.github.io/openai-agents-js/openai/agents/classes/runtoolapprovalitem/).
- Also see [the openai human-in-the-loop guide](https://openai.github.io/openai-agents-js/guides/human-in-the-loop/#approval-requests).
- Also see [MCP Approval Requests from OpenAI](https://platform.openai.com/docs/guides/tools-remote-mcp#approvals).

### ChatClientAgent Approval Process Flow

1. User asks agent to perform a task and request is added to the thread.
1. Agent calls model with registered functions.
1. Model responds with function calls to make.
1. ConfirmingFunctionInvokingChatClient decorator (new feature / enhancement to FunctionInvokingChatClient) identifies any function calls that require user approval and returns an ApprovalRequestContent.
   ChatClient implementations should also convert any approval requests from the service into ApprovalRequestContent.
1. Agent updates the thread with the FunctionCallContent (or this may have already been done by a service threaded agent) if the approval request is for a function call.
1. Agent stores the ApprovalRequestContent in its AgentThread under ActiveApprovalRequests, so that it knows that there is an outstanding user request.
1. Agent returns the ApprovalRequestContent to the caller which shows it to the user in the appropriate format.
1. User (via caller) invokes the agent again with ApprovalResponseContent.
1. Agent removes the ApprovalRequestContent from its AgentThread ActiveApprovalRequests.
1. Agent invokes IChatClient with ApprovalResponseContent and the ConfirmingFunctionInvokingChatClient decorator identifies the response as an approval for the function call.
   If it isn't an approval for a manual function call, it can be passed through to the underlying ChatClient to be converted to the appropriate Approval content type for the service.
1. ConfirmingFunctionInvokingChatClient decorator invokes the function call and invokes the underlying IChatClient with a FunctionResultContent.
1. Model responds with the result.
1. Agent responds to caller with result message and thread is updated with the result message.

At construction time the set of functions that require user approval will need to be registered with the `ConfirmingFunctionInvokingChatClient` decorator
so that it can identify which function calls should be returned as an `ApprovalRequestContent`.

### CustomAgent Approval Process Flow

1. User asks agent to perform a task and request is added to the thread.
1. Agent executes various steps.
1. Agent encounters a step for which it requires user approval to continue.
1. Agent responds with an ApprovalRequestContent.
1. Agent updates its own state with the progress that it has made up to that point and adds the ApprovalRequestContent to its AgentThread ActiveApprovalRequests.
1. User (via caller) invokes the agent again with ApprovalResponseContent.
1. Agent loads its progress from state and continues processing.
1. Agent removes its ApprovalRequestContent from its AgentThread ActiveApprovalRequests.
1. Agent responds to caller with result message and thread is updated with the result message.

## Open Questions

## Decision Outcome
