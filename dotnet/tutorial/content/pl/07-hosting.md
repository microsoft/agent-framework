# Hostowanie agenta

**Przykład:** `dotnet/samples/01-get-started/06_host_your_agent/`

Pakiet `Microsoft.Agents.AI.Hosting.AzureFunctions` pozwala hostować dowolny `AIAgent` jako aplikację Azure Functions. Automatycznie generuje endpointy HTTP i używa Durable Functions do stanowych, długotrwałych rozmów.

## Kompletny program

```csharp
// Copyright (c) Microsoft. All rights reserved.

// Ten przykład pokazuje, jak hostować agenta AI w Azure Functions (DurableAgents).
//
// Wymagania wstępne:
//   - Azure Functions Core Tools
//   - Klucz API OpenAI
//
// Zmienne środowiskowe:
//   OPENAI_API_KEY
//   OPENAI_MODEL (domyślnie "gpt-4o-mini")
//
// Uruchom za pomocą: func start
// Następnie wywołaj: POST http://localhost:7071/api/agents/HostedAgent/run

using Microsoft.Agents.AI;
using Microsoft.Agents.AI.Hosting.AzureFunctions;
using Microsoft.Azure.Functions.Worker.Builder;
using Microsoft.Extensions.Hosting;
using OpenAI;
using OpenAI.Chat;

var apiKey = Environment.GetEnvironmentVariable("OPENAI_API_KEY")
    ?? throw new InvalidOperationException("OPENAI_API_KEY is not set.");
var model = Environment.GetEnvironmentVariable("OPENAI_MODEL") ?? "gpt-4o-mini";

// Skonfiguruj agenta AI zgodnie ze standardowym wzorcem MAF.
AIAgent agent = new OpenAIClient(apiKey)
    .GetChatClient(model)
    .AsAIAgent(
        instructions: "Jesteś pomocnym asystentem hostowanym w Azure Functions.",
        name: "HostedAgent");

// Skonfiguruj aplikację funkcji do hostowania agenta AI.
// Spowoduje to automatyczne wygenerowanie endpointów HTTP API dla agenta.
using IHost app = FunctionsApplication
    .CreateBuilder(args)
    .ConfigureFunctionsWebApplication()
    .ConfigureDurableAgents(options => options.AddAIAgent(agent, timeToLive: TimeSpan.FromHours(1)))
    .Build();

app.Run();
```

## Jak działa DurableAgents

Rozszerzenie `ConfigureDurableAgents` opakowuje Twój `AIAgent` orkiestracją Azure Durable Functions:

```
Klient → POST /api/agents/{name}/run
              ↓
         Orkiestrator Durable (zarządza cyklem życia sesji)
              ↓
         Twój AIAgent.RunAsync(message, session)
              ↓
         OpenAI API
```

Sesje są automatycznie utrwalane w magazynie stanów Durable Functions — bez pisania kodu bazy danych. Parametr `timeToLive` określa, kiedy nieaktywne sesje są czyszczone.

## Generowane endpointy HTTP

Po uruchomieniu `func start` dostępne są następujące endpointy:

| Metoda | Ścieżka | Opis |
|---|---|---|
| `POST` | `/api/agents/{name}/run` | Rozpocznij nową rozmowę lub kontynuuj istniejącą |
| `GET` | `/api/agents/{name}/sessions/{sessionId}` | Pobierz metadane sesji |
| `DELETE` | `/api/agents/{name}/sessions/{sessionId}` | Usuń sesję |

### Przykład: Rozpoczęcie rozmowy

```bash
curl -X POST http://localhost:7071/api/agents/HostedAgent/run \
     -H "Content-Type: application/json" \
     -d '{"message": "Cześć!"}'
```

Odpowiedź:
```json
{
  "sessionId": "abc123",
  "response": "Cześć! W czym mogę Ci pomóc?"
}
```

### Przykład: Kontynuowanie rozmowy

```bash
curl -X POST http://localhost:7071/api/agents/HostedAgent/run \
     -H "Content-Type: application/json" \
     -d '{"sessionId": "abc123", "message": "Co właśnie powiedziałem?"}'
```

## Uruchamianie lokalnie

### Wymagania wstępne

```bash
# Zainstaluj Azure Functions Core Tools
npm install -g azure-functions-core-tools@4 --unsafe-perm true
```

### Uruchomienie

```bash
cd dotnet/samples/01-get-started/06_host_your_agent
func start
```

### Test

```bash
curl -X POST http://localhost:7071/api/agents/HostedAgent/run \
     -H "Content-Type: application/json" \
     -d '{"message": "Opowiedz mi żart."}'
```

## Wdrożenie na Azure

Przykład działa lokalnie za pomocą Azure Functions Core Tools. Aby wdrożyć na Azure:

```bash
# Utwórz aplikację funkcji (wymaga Azure CLI)
az functionapp create \
    --resource-group mojaGrupaZasobow \
    --name moj-agent-maf \
    --storage-account mojeKontoStorage \
    --runtime dotnet-isolated \
    --runtime-version 9 \
    --functions-version 4

# Wdróż
func azure functionapp publish moj-agent-maf
```

Ustaw te same zmienne środowiskowe (`OPENAI_API_KEY`, `OPENAI_MODEL`) jako Ustawienia aplikacji w portalu Azure.

## Kluczowe wnioski

- `ConfigureDurableAgents` to jedno wywołanie metody — obsługuje routing HTTP, utrwalanie sesji i TTL
- Każdy `AIAgent` (z narzędziami, pamięcią itp.) działa jako hostowany agent
- Sesje są utrwalane automatycznie przez Durable Functions
- To samo HTTP API działa lokalnie i na Azure
- `timeToLive` kontroluje, jak długo nieaktywne sesje są przechowywane przed czyszczeniem
