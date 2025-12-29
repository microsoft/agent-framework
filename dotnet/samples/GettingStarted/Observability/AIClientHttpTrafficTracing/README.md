# AIClient HTTP Traffic Tracing

This sample shows how to enable **HTTP request/response logging** for LLM calls (including request/response bodies) for any `AIClient`.

It uses the `ClientLoggingOptions` pipeline to print HTTP details to the `ILogger` so you can troubleshoot prompts, headers, and responses.

## Prerequisites

- Azure CLI login (this sample uses `AzureCliCredential`):
  - `az login`
- Environment variables:
  - `AZURE_OPENAI_ENDPOINT` (e.g. `https://{resource-name}.openai.azure.com/`)
  - `AZURE_OPENAI_DEPLOYMENT_NAME` (optional; defaults to `gpt-4o-mini`)

Switch to OpenAI Compatible SDK using below code
```csharp
var clientOptions = new OpenAIClientOptions()
{
    Endpoint = new Uri("https://endpoint"),
    ClientLoggingOptions = clientLoggingOptions
};
new OpenAIClient(new ApiKeyCredential("<apiKey/accessKey>"), clientOptions)
.GetChatClient("modelName")
.AsIChatClient();
```

## Run

From the repo root:

```powershell
cd samples\GettingStarted\Observability\AIClientHttpTrafficTracing
dotnet run
```

## Enable HTTP traffic logging

This sample enables logging in two places:

1. **Enable HTTP logging on the client**

In [Program.cs](Program.cs), the sample configures:

- `ClientLoggingOptions.EnableLogging = true`
- `ClientLoggingOptions.EnableMessageLogging = true` (URL + headers + query parameters)
- `ClientLoggingOptions.EnableMessageContentLogging = true` (request/response bodies)
- `ClientLoggingOptions.MessageContentSizeLimit` to cap how much body content is written

`ClientLoggingOptions` is a common pattern across SDK clients that expose these options (for example, via a `ClientLoggingOptions` property on client options like `AzureOpenAIClientOptions`).

2. **Raise the log level to `Debug` only if you want request/response bodies**

URL/headers/query parameter logging (step 1) is normally available at `Information` level and step 2 is not needed.

Request/response *body* logging is emitted at `Debug` level by the underlying message logging policy. The sample sets:

- `System.ClientModel.Primitives.MessageLoggingPolicy` → `Debug`

## Security notes

- Logging bodies can include sensitive prompt/response data. Use only in dev/test.
- Headers like `Authorization` are **redacted by default**. While it is technically possible to allow logging a sensitive header (for example, via `clientLoggingOptions.AllowedHeaderNames.Add("Authorization")`), **do not enable this in production or long-lived environments**. If you must temporarily log such headers for debugging, do so only in tightly controlled, short-lived sessions, treat the logs as secrets, and securely delete them immediately after use.

## Using ASP.NET Core configuration

If you’re using ASP.NET Core, you can set the log level in `appsettings.json` instead of calling `AddFilter`, for example:

```json
{
  "Logging": {
    "LogLevel": {
      "Default": "Information",
      "Microsoft.AspNetCore": "Warning",
      "System.ClientModel.Primitives.MessageLoggingPolicy": "Debug"
    }
  }
}
```
