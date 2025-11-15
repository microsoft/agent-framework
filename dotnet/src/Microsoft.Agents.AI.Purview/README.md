# Microsoft Agent Framework - Purview Integration (Dotnet)

The Purview plugin for the Microsoft Agent Framework adds Purview policy evaluation to the Microsoft Agent Framework.
It lets you enforce data security and governance policies on both the *prompt* (user input + conversation history) and the *model response* before they proceed further in your workflow.

> Status: **Preview**

### Key Features

- Middleware-based policy enforcement (agent-level and chat-client level)
- Blocks or allows content at both ingress (prompt) and egress (response)
- Works with any `IChatClient` or `AIAgent` using the standard Agent Framework middleware pipeline.
- Authenticates to Purview using `TokenCredential`s
- Simple configuration using `PurviewSettings`
- Configurable caching using `IDistributedCache`
- `WithPurview` Extension methods to easily apply middleware to a `ChatClientBuilder` or `AIAgentBuilder`

### When to Use
Add Purview when you need to:

- Prevent sensitive or disallowed content from being sent to an LLM
- Prevent model output containing disallowed data from leaving the system
- Apply centrally managed policies without rewriting agent logic

---


## Quick Start

``` csharp
using Azure.AI.OpenAI;
using Azure.Core;
using Azure.Identity;
using Microsoft.Agents.AI;
using Microsoft.Agents.AI.Purview;
using Microsoft.Extensions.AI;

Uri endpoint = new Uri("..."); // The endpoint of Azure OpenAI instance.
string deploymentName = "..."; // The deployment name of your Azure OpenAI instance ex: gpt-4o-mini
string purviewClientAppId = "..."; // The client id of your entra app registration. 

// This will get a user token for an entra app configured to call the Purview API.
// Any TokenCredential with permissions to call the Purview API can be used here.
TokenCredential browserCredential = new InteractiveBrowserCredential(
    new InteractiveBrowserCredentialOptions
    {
        ClientId = purviewClientAppId
    });

IChatClient client = new AzureOpenAIClient(
    new Uri(endpoint),
    new AzureCliCredential())
    .GetOpenAIResponseClient(deploymentName)
    .AsIChatClient()
    .AsBuilder()
    .WithPurview(browserCredential, new PurviewSettings("My Sample App"))
    .Build();

using (client)
{
    Console.WriteLine("Enter a prompt to send to the client:");
    string? promptText = Console.ReadLine();

    if (!string.IsNullOrEmpty(promptText))
    {
        // Invoke the agent and output the text result.
        Console.WriteLine(await client.GetResponseAsync(promptText));
    }
}
```

If a policy violation is detected on the prompt, the middleware interrupts the run and outputs the message: `"Prompt blocked by policies"`. If on the response, the result becomes `"Response blocked by policies"`.

---

## Authentication

The Purview middleware uses Azure.Core TokenCredential objects for authentication.

The plugin requires the following Graph permissions:
- ProtectionScopes.Compute.All : [userProtectionScopeContainer](https://learn.microsoft.com/en-us/graph/api/userprotectionscopecontainer-compute)
- Content.Process.All : [processContent](https://learn.microsoft.com/en-us/graph/api/userdatasecurityandgovernance-processcontent)
- ContentActivity.Write : [contentActivity](https://learn.microsoft.com/en-us/graph/api/activitiescontainer-post-contentactivities)

Authentication with user tokens is preferred. If authenticating with app tokens, the agent-framework caller will need to provide an entra user id for each `ChatMessage` send to the agent/client. This user id can be set using the `SetUserId` extension method, or by setting the `"userId"` field of the `AdditionalProperties` dictionary.

``` csharp
// Manually
var message = new ChatMessage(ChatRole.User, promptText);
if (message.AdditionalProperties == null)
{
    message.AdditionalProperties = new AdditionalPropertiesDictionary();
}
message.AdditionalProperties["userId"] = "<your-entra-user-id-here>";

// Or with the extension method
var message = new ChatMessage(ChatRole.User, promptText);
message.SetUserId(new Guid("<your-entra-user-id-here>"));
```

### Tenant Enablement for Purview
- The tenant requires an e5 license and consumptive billing setup.
- [Data Loss Prevention](https://learn.microsoft.com/en-us/purview/dlp-create-deploy-policy) or [Data Collection Policies](https://learn.microsoft.com/en-us/purview/collection-policies-policy-reference) policies that apply to the user are required to enable classification and message ingestion (Process Content API). Otherwise, messages will only be logged in Purview's Audit log (Content Activities API).

## Configuration

### Settings

The Purview middleware can be customized and configured using the `PurviewSettings` class.

#### `PurviewSettings`

| Field | Type | Purpose |
| ----- | ---- | ------- |
| AppName | string | The publicly visible app name of the application. |
| AppVersion | string? | (Optional) The version string of the application. |
| TenantId | string? | (Optional) The tenant id of the user making the request. If not provided, this will be inferred from the token. |
| PurviewAppLocation | PurviewAppLocation? | (Optional) The location of the Purview resource used during policy evaluation. If not provided, a location containing the application client id will be used instead. |
| IgnoreExceptions | bool | (Optional, `false` by default) Determines if the exceptions thrown in the Purview middleware should be ignored. If set to true, exceptions will be logged but not thrown. |
| GraphBaseUri | Uri | (Optional, https://graph.microsoft.com/v1.0/ by default) The base URI used for calls to Purview's Microsoft Graph APIs. |
| BlockedPromptMessage | string | (Optional, `"Prompt blocked by policies"` by default) The message returned when a prompt is blocked by Purview. |
| BlockedResponseMessage | string | (Optional, `"Response blocked by policies"` by default) The message returned when a response is blocked by Purview. |
| InMemoryCacheSizeLimit | long? | (Optional, `100_000_000` by default) The size limit of the default in-memory cache in bytes. This only applies if no cache is provided when creating the Purview middleware. |
| CacheTTL | TimeSpan | (Optional, 30 minutes by default) The time to live of each cache entry. |
| PendingBackgroundJobLimit | int | (Optional, 100 by default) The maximum number of pending background jobs that can be queued in the middleware. |
| MaxConcurrentJobConsumers | int | (Optional, 10 by default) The maximum number of concurrent consumers that can run background jobs in the middleware. |

#### `PurviewAppLocation`

| Field | Type | Purpose |
| ----- | ---- | ------- |
| LocationType | PurviewLocationType | The type of the location: Application, Uri, Domain. |
| LocationValue | string | The value of the location. |

#### Location

The `PurviewAppLocation` field of the `PurviewSettings` object contains the location of the app which is used by Purview for policy evaluation (see [policyLocation](https://learn.microsoft.com/en-us/graph/api/resources/policylocation?view=graph-rest-1.0) for more information). 
This location can be set to the URL of the agent app, the domain of the agent app, or the application id of the agent app.

#### Example

```csharp
var location = new PurviewAppLocation(PurviewLocationType.Uri, "https://contoso.com/chatagent");
var settings = new PurviewSettings("My Sample App")
{
    AppVersion = "1.0",
    TenantId = "your-tenant-id",
    PurviewAppLocation = location,
    IgnoreExceptions = false,
    GraphBaseUri = new Uri("https://graph.microsoft.com/v1.0/"),
    BlockedPromptMessage = "Prompt blocked by policies.",
    BlockedResponseMessage = "Response blocked by policies.",
    InMemoryCacheSizeLimit = 100_000_000,
    CacheTTL = TimeSpan.FromMinutes(30),
    PendingBackgroundJobLimit = 100,
    MaxConcurrentJobConsumers = 10,
};

// ... Set up credential and client builder ...

var client = builder.WithPurview(credential, settings).Build();
```

#### Customizing Blocked Messages

This is useful for:
- Providing more user-friendly error messages
- Including support contact information
- Localizing messages for different languages
- Adding branding or specific guidance for your application

``` csharp
var settings = new PurviewSettings("My Sample App")
{
    BlockedPromptMessage = "Your request contains content that violates our policies. Please rephrase and try again.",
    BlockedResponseMessage = "The response was blocked due to policy restrictions. Please contact support if you need assistance.",
};
```

### Selecting Agent vs Chat Middleware

Use the agent middleware when you already have / want the full agent pipeline:

``` csharp
AIAgent agent = new AzureOpenAIClient(
    new Uri(endpoint),
    new AzureCliCredential())
    .GetChatClient(deploymentName)
    .CreateAIAgent("You are a helpful assistant.")
    .AsBuilder()
    .WithPurview(browserCredential, new PurviewSettings("Agent Framework Test App"))
    .Build();
```

Use the chat middleware when you attach directly to a chat client (e.g. minimal agent shell or custom orchestration):

``` csharp
IChatClient client = new AzureOpenAIClient(
    new Uri(endpoint),
    new AzureCliCredential())
    .GetOpenAIResponseClient(deploymentName)
    .AsIChatClient()
    .AsBuilder()
    .WithPurview(browserCredential, new PurviewSettings("Agent Framework Test App"))
    .Build();
```

The policy logic is identical; the only difference is the hook point in the pipeline.

---

## Middleware Lifecycle
1. Before sending the prompt to the agent, the middleware checks the app and user metadata against Purview's protection scopes and evaluates all the `ChatMessage`s in the prompt.
2. If the content was blocked, the middleware returns a `ChatResponse` or `AgentRunResponse` containing the `BlockedPromptMessage` text. The blocked content does not get passed to the agent.
3. If the evaluation did not block the content, the middleware passes the prompt data to the agent and waits for a response.
4. After receiving a response from the agent, the middleware calls Purview again to evaluate the response content.
5. If the content was blocked, the middleware returns a response containing the `BlockedResponseMessage`.

The user id from the prompt message(s) is reused for the response evaluation so both evaluations map consistently to the same user.

There are several optimizations to speed up Purview calls. Protection scope lookups (the first step in evaluation) are cached to minimize network calls. 
If the policies allow content to be processed offline, the middleware will add the process content request to a channel and run it in a background worker. Similarly, the middleware will run a background request if no scopes apply and the interaction only has to be logged in Audit.

## Exceptions
| Exception | Scenario |
| --------- | -------- |
| PurviewAuthenticationException | Token acquisition / validation issues |
| PurviewJobException | Errors thrown by a background job |
| PurviewJobLimitExceededException | Errors caused by exceeding the background job limit |
| PurviewPaymentRequiredException | 402 responses from the service |
| PurviewRateLimitException | 429 responses from the service |
| PurviewRequestException | Other errors related to Purview requests |
| PurviewException | Base class for all Purview plugin exceptions |

Callers' exception handling can be fine-grained

``` csharp
try
{
    // Code that uses Purview middleware
}
catch (PurviewPaymentRequiredException)
{
    this._logger.LogError("Payment required for Purview.");
}
catch (PurviewAuthenticationException)
{
    this._logger.LogError("Error authenticating to Purview.");
}
```

Or broad

``` csharp
try
{
    // Code that uses Purview middleware
}
catch (PurviewException e)
{
    this._logger.LogError(e, "Purview middleware threw an exception.")
}
```
