# Per-Run MCP Authentication Headers

This sample shows how to attach per-run (refreshable) authentication headers to Model Context
Protocol (MCP) requests using existing Agent Framework primitives. It addresses scenarios where the
header value changes from one run to the next, for example a short-lived On-Behalf-Of (OBO) or cloud
identity token that expires and must be refreshed.

The agent backend is Microsoft Foundry accessed through the Responses API (RAPI). The MCP server is
the public Microsoft Learn MCP server.

## What this sample demonstrates

- A custom `HttpClient` on the MCP transport whose `DelegatingHandler` stamps an `Authorization`
  header on every outbound MCP request.
- An `AsyncLocal` scope (`McpRunScope`) that carries the current run's context to the handler, set
  immediately before each run and cleared in a `finally` block.
- Running the same agent twice under two different contexts, each with a freshly minted token, so the
  header is per-run rather than fixed when the agent or the MCP connection was created.

Because the handler reads the token fresh on every request, an expiring token is refreshed simply by
placing a new value in scope before the next run. No agent or connection rebuild is required.

## How it works

```text
RunForContextAsync sets McpRunScope.Current
        -> agent.RunAsync invokes an MCP tool
                -> PerRunAuthHeaderHandler reads McpRunScope.Current
                        -> stamps Authorization: Bearer <token> on the MCP request
RunForContextAsync clears McpRunScope.Current in finally
```

The public Microsoft Learn MCP server is anonymous and ignores the demonstration token. In production
you point the handler at your own protected MCP server and mint a real token per run.

## Prerequisites

- .NET 10 SDK or later
- A Microsoft Foundry project endpoint and a model deployment
- An authenticated Azure identity (for example, sign in with `az login`)

Set the following environment variables:

```powershell
$env:FOUNDRY_PROJECT_ENDPOINT="https://your-foundry-service.services.ai.azure.com/api/projects/your-foundry-project"
$env:FOUNDRY_MODEL="gpt-5.4-mini"
```

## Run the sample

```powershell
dotnet run
```

## Security considerations

This sample is written to demonstrate the pattern safely. When you adapt it, keep these in place:

- **Never log the token.** Only the non-secret label is printed. Avoid printing the token even in a
  masked form.
- **Attach the header over HTTPS only.** The handler skips the header when the request is not HTTPS,
  so a credential is never sent over plaintext.
- **Scope the header to the MCP server origin.** The handler attaches the header only when the
  request targets the configured server origin (scheme, host, and port). Auto-redirect is also
  disabled (`AllowAutoRedirect = false`) so a redirect cannot carry the token to another origin
  below the handler before the origin check runs.
- **Reset the scope after each run.** `McpRunScope.Current` is restored to its prior value in a
  `finally` block so a token does not bleed into later, unrelated work and nesting stays safe.
- **Disable cookies on the shared handler.** `UseCookies = false` avoids cross-context state on a
  shared client, and `CheckCertificateRevocationList = true` validates the server certificate.
- **Use non-identifying labels and tokens.** The labels and tokens here carry no personal data and are
  regenerated per run.
- **Do not persist secrets in serialized session state.** Agent session state is serializable, so keep
  raw tokens in memory or mint them per run rather than storing them there.

## Production notes

- Replace the demonstration token with a real per-request exchange inside the handler, for example an
  Azure `TokenCredential`, MSAL OBO flow, or a cloud identity token. Performing the exchange per
  request lets expiry self-heal because each request obtains a current token.
- The `AsyncLocal` scope isolates concurrent runs from each other, so parallel runs with different
  tokens do not interfere.
- As an alternative carrier, the token can be read from `AgentSession` state by an `AIContextProvider`
  that copies it into the scope at the start of each invocation. Remember the serialized-state warning
  above and avoid persisting the raw secret.
- For MCP servers that implement standard OAuth, `HttpClientTransportOptions.OAuth` already handles the
  authorization and refresh flow, so a custom handler is unnecessary.
- This sample attaches the same header for every tool call in a run. Selecting different headers based
  on the specific tool or its arguments is intentionally out of scope here.
