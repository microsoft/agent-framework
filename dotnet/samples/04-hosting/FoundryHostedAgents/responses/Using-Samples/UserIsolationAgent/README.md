# User Isolation Agent

This client demonstrates delegated user identity for a middle tier that serves several application
users through one Foundry hosted session.

The sample creates one shared hosted session. Each user receives a separate Agent Framework
`AgentSession`, and every invocation sends that user's stable identifier through
`ChatOptions.WithFoundryHostedAgentUserIdentity`. Agent Framework places the value in the
`x-ms-user-identity` request header.

## What Foundry isolates

The middle tier authenticates Alice and Bob before calling Foundry. It then sends a stable application
identifier for the authenticated user:

```text
Alice AgentSession + shared agent_session_id + x-ms-user-identity: alice
Bob   AgentSession + shared agent_session_id + x-ms-user-identity: bob
```

Foundry resolves that delegated identity and isolates platform managed conversation history. Bob cannot
continue Alice's response chain, even though both users share the same hosted sandbox.

The sample deliberately creates one `AgentSession` per user. Reusing one `AgentSession` for different
users would also reuse its conversation continuation identifier. Foundry rejects that cross user
continuation rather than exposing the first user's history.

## What the application must isolate

Foundry isolates the conversation history it manages. It does not automatically partition arbitrary
files, database rows, or cache entries written by the container. If the hosted agent stores its own
user data, partition that data by both the hosted session identifier and the resolved user identifier:

```text
(agent_session_id, user_id)
```

Do not trust a user identifier copied directly from an untrusted client request. The middle tier must
authenticate the user, authorize the requested action, and choose the stable identifier that it sends
to Foundry.

## Configure the calling principal

The identity represented by `AzureCliCredential` in this sample is acting as the trusted middle tier.
In production this is normally a managed identity or service principal. That principal needs both:

1. Permission to invoke the agent endpoint. `Foundry Agent Consumer` is the least privilege built in role.
2. Permission to send `x-ms-user-identity`. This permission is not included in a built in role and must
   be granted through a custom role.

Create `custom-impersonation-role.json`:

```json
{
  "Name": "Foundry Agent User Identity Impersonation",
  "IsCustom": true,
  "Description": "Lets a trusted middle-tier service delegate an end-user identity to a hosted agent.",
  "Actions": [],
  "NotActions": [],
  "DataActions": [
    "Microsoft.CognitiveServices/accounts/AIServices/agents/endpoints/UserIdentityImpersonation/action"
  ],
  "NotDataActions": [],
  "AssignableScopes": [
    "/subscriptions/<subscription-id>/resourceGroups/<resource-group>/providers/Microsoft.CognitiveServices/accounts/<account-name>"
  ]
}
```

Create and assign the role:

```powershell
az role definition create --role-definition custom-impersonation-role.json

az role assignment create `
  --assignee <middle-tier-principal-object-id> `
  --role "Foundry Agent User Identity Impersonation" `
  --scope "/subscriptions/<subscription-id>/resourceGroups/<resource-group>/providers/Microsoft.CognitiveServices/accounts/<account-name>"
```

The role can be assigned at the Foundry project or specific agent scope when your deployment model
supports that narrower scope. A caller that sends `x-ms-user-identity` without this data action receives
HTTP 403.

The delegated identifier is not an access token and this flow is not OAuth on behalf of token exchange.
The middle tier authenticates the user itself, then Foundry accepts the identifier only because the
calling principal has the explicit impersonation data action.

## Prerequisites

* [.NET 10 SDK](https://dotnet.microsoft.com/download/dotnet/10.0)
* A hosted agent deployed with Responses protocol version 2.0.0
* Azure CLI authenticated with `az login`
* Session administration permission for the sample's create and delete operations
* The invocation and impersonation permissions described above

User isolation is a platform behavior. It is not enforced by a local `dotnet run` agent server, so this
sample targets a deployed Foundry agent.

## Configuration

Copy `.env.example` to `.env` and set:

```env
FOUNDRY_PROJECT_ENDPOINT=https://<account>.services.ai.azure.com/api/projects/<project>
AZURE_AI_AGENT_NAME=<deployed-hosted-agent-name>
```

## Run

```powershell
cd dotnet\samples\04-hosting\FoundryHostedAgents\responses\Using-Samples\UserIsolationAgent
dotnet run
```

Enter `alice`, send several messages, then enter `bob`. Returning to `alice` reuses Alice's own
`AgentSession`. Both users remain attached to the one hosted session printed at startup.

## Related documentation

* [Multiplex multiple users in one hosted agent session](https://learn.microsoft.com/azure/foundry/agents/how-to/multiplex-session-users)
* [Hosted agent permissions reference](https://learn.microsoft.com/azure/foundry/agents/concepts/hosted-agent-permissions#delegate-the-end-user-identity)
