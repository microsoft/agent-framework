# Copilot Studio agent

Use `CopilotStudioAgent` to call an existing, published Copilot Studio agent through
the Agent Framework `AIAgent` API. This console sample signs in a user, streams
responses, and preserves the conversation across follow-up questions.

## Prerequisites

- .NET 10 SDK.
- A published Copilot Studio agent and a user who can access it.
- A Microsoft Entra public client app registration in the agent's tenant with
  the delegated `CopilotStudio.Copilots.Invoke` permission and any required consent.
  Configure the mobile/desktop redirect URI `http://localhost` for browser sign-in.
- The Microsoft 365 Agents SDK connection URL from the agent's **Channels >
  Native app** settings. Use that URL, not a Direct Line token endpoint.

Follow the [Copilot Studio client setup guide](https://learn.microsoft.com/microsoft-copilot-studio/publication-integrate-web-or-native-app-m365-agents-sdk)
for app registration and channel setup.

## Configure and run

Set these variables in the terminal where you run the sample:

```powershell
$env:COPILOT_STUDIO_TENANT_ID = "<tenant-id>"
$env:COPILOT_STUDIO_CLIENT_ID = "<public-client-app-id>"
$env:COPILOT_STUDIO_DIRECT_CONNECT_URL = "<Microsoft 365 Agents SDK connection URL>"
dotnet run
```

The browser opens when the first request needs a token. Ask a question supported
by your agent, then a follow-up question in the same conversation. Enter `/exit`
to finish. The sample uses a public client and does not require a client secret.

Only accept the connection URL from trusted application configuration. The token
handler obtains a token for `CopilotClient.ScopeFromSettings(settings)` on each
request; `InteractiveBrowserCredential` handles caching and renewal. HTTP redirects
are disabled. For a service application, choose an authentication flow supported
by your Copilot Studio deployment rather than using interactive browser sign-in.

## Agent and session lifecycle

`CopilotClient` handles the Copilot Studio connection and authentication transport.
`CopilotStudioAgent` adapts that client to `RunAsync` and `RunStreamingAsync`.
In an application outside this repository, reference the
`Microsoft.Agents.AI.CopilotStudio` package (currently a preview package).

Create a session with `await agent.CreateSessionAsync()` and pass it to every turn
that should share a conversation. The remote conversation starts on the first
run. Omitting the session on successive runs starts separate conversations.
For a non-streaming response, use `await agent.RunAsync(input, session)`.

The sample serializes and deserializes the session after each turn to demonstrate
restoring the remote conversation reference. It keeps the JSON only in memory, so
restarting the console starts a new conversation. A host can save that JSON using
`SerializeSessionAsync` and restore it using `DeserializeSessionAsync`. Store it
under the authenticated caller's identity and authorize retrieval before reuse;
a conversation identifier is not an authorization boundary.

If you already have a conversation ID, `await agent.CreateSessionAsync(conversationId)`
creates a session referring to that conversation. Session serialization preserves
the reference, not a local copy of the server's full conversation history.

## Input and output

This is a text console. The adapter joins the text from input messages into the
question sent to Copilot Studio; it does not upload arbitrary `AIContent` inputs.
The console prints each update's `Text`. Copilot Studio activities can also carry
cards and other content that require an application-specific renderer. Streaming
updates follow the activities returned by the service, so do not assume every
update is a single model token.

If sign-in or invocation fails, check the tenant, app registration, delegated
permission/consent, published agent access, and connection URL before retrying.
