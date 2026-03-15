# Wprowadzenie do Microsoft Agent Framework

**Microsoft Agent Framework (MAF)** to biblioteka .NET do budowania agentów AI — autonomicznych programów, które rozumują, pamiętają i działają przy użyciu dużych modeli językowych.

MAF zapewnia przejrzyste, kompozycyjne API zbudowane na bazie `Microsoft.Extensions.AI`, ułatwiając:

- Tworzenie agentów obsługiwanych przez dowolnego dostawcę LLM (OpenAI, Anthropic, Azure OpenAI i inne)
- Wyposażanie agentów w narzędzia (funkcje lokalne, zewnętrzne API)
- Utrzymywanie wieloturowych rozmów ze stanem sesji
- Budowanie złożonych przepływów pracy z wieloma agentami
- Hostowanie agentów jako usług produkcyjnych

## Dlaczego MAF?

| Bez MAF | Z MAF |
|---|---|
| Ręczne wywołania HTTP do API modeli LLM | `agent.RunAsync("...")` |
| Ręczne śledzenie historii rozmowy | `AgentSession` obsługuje to automatycznie |
| Własna implementacja wywoływania funkcji | Dekoruj metody atrybutem `[Description]` |
| Niestandardowa orkiestracja | `WorkflowBuilder` + krawędzie |

## Pierwsze kroki

### Wymagania wstępne

- SDK .NET 10
- Klucz API OpenAI (lub Anthropic — patrz niżej)
- Dwie zmienne środowiskowe:

```bash
export OPENAI_API_KEY="sk-..."
export OPENAI_MODEL="gpt-4o-mini"
```

### Tworzenie nowej aplikacji .NET

Utwórz nową aplikację konsolową i dodaj wymagane pakiety NuGet:

```bash
dotnet new console -n MyAgent
cd MyAgent
```

#### Pakiety NuGet dla OpenAI

```bash
dotnet add package Microsoft.Agents.AI --prerelease
dotnet add package Microsoft.Agents.AI.OpenAI --prerelease
dotnet add package Microsoft.Extensions.AI.OpenAI
dotnet add package Azure.AI.OpenAI --prerelease
```

#### Pakiety NuGet dla Anthropic (Claude)

Jeśli chcesz używać Claude zamiast OpenAI, zainstaluj adapter Anthropic:

```bash
dotnet add package Microsoft.Agents.AI --prerelease
dotnet add package Microsoft.Agents.AI.Anthropic --prerelease
dotnet add package Anthropic
```

#### Do czego służy każdy pakiet

| Pakiet | Przeznaczenie |
|---|---|
| `Microsoft.Agents.AI` | Główna biblioteka MAF — `AIAgent`, `AgentSession`, `WorkflowBuilder`, obsługa narzędzi |
| `Microsoft.Agents.AI.OpenAI` | Adapter MAF dla OpenAI — dodaje `.AsAIAgent()` do `IChatClient` |
| `Microsoft.Extensions.AI.OpenAI` | Oficjalny most OpenAI firmy Microsoft dla `Microsoft.Extensions.AI` |
| `Azure.AI.OpenAI` | Azure OpenAI SDK (używany również dla standardowych punktów końcowych openai.com) |
| `Microsoft.Agents.AI.Anthropic` | Oficjalny adapter MAF dla Anthropic — dodaje `.AsAIAgent()` bezpośrednio do `AnthropicClient` |
| `Anthropic` | Oficjalny SDK Anthropic dla .NET (`AnthropicClient`, strumieniowanie modeli itp.) |

> **Dlaczego `Microsoft.Agents.AI.Anthropic` i `Anthropic` osobno?**
> Pakiet `Anthropic` to własny SDK Anthropic obsługujący transport HTTP.
> `Microsoft.Agents.AI.Anthropic` opakowuje go w abstrakcję `AIAgent` MAF — dzięki temu sesje, narzędzia, pamięć i przepływy pracy działają tak samo jak w OpenAI.

### Twój pierwszy agent (5 linii)

```csharp
using Microsoft.Agents.AI;
using OpenAI;
using OpenAI.Chat;

var apiKey = Environment.GetEnvironmentVariable("OPENAI_API_KEY")
    ?? throw new InvalidOperationException("OPENAI_API_KEY is not set.");
var model = Environment.GetEnvironmentVariable("OPENAI_MODEL") ?? "gpt-4o-mini";

AIAgent agent = new OpenAIClient(apiKey)
    .GetChatClient(model)
    .AsAIAgent(instructions: "Jesteś pomocnym asystentem.");

Console.WriteLine(await agent.RunAsync("Cześć!"));
```

Kluczową metodą rozszerzającą jest `.AsAIAgent()` — opakowuje dowolny `IChatClient` w pełnoprawny obiekt `AIAgent`.

### Alternatywa: Anthropic (Claude)

MAF posiada oficjalną integrację z Anthropic przez pakiet `Microsoft.Agents.AI.Anthropic`. Wzorzec jest nieco inny — `AnthropicClient` udostępnia `.AsAIAgent()` bezpośrednio:

```bash
export ANTHROPIC_API_KEY="sk-ant-..."
export ANTHROPIC_MODEL="claude-haiku-4-5"
```

```csharp
using Anthropic;
using Microsoft.Agents.AI;

var apiKey = Environment.GetEnvironmentVariable("ANTHROPIC_API_KEY")
    ?? throw new InvalidOperationException("ANTHROPIC_API_KEY is not set.");
var model = Environment.GetEnvironmentVariable("ANTHROPIC_MODEL") ?? "claude-haiku-4-5";

using AnthropicClient client = new AnthropicClient() { ApiKey = apiKey };

AIAgent agent = client.AsAIAgent(
    model: model,
    instructions: "Jesteś pomocnym asystentem.");

Console.WriteLine(await agent.RunAsync("Cześć!"));
```

Reszta tutoriala używa OpenAI, ale każdy wzorzec — sesje, narzędzia, pamięć, przepływy pracy — działa identycznie z Anthropic.

## Struktura tutoriala

Ten tutorial omawia sześć oficjalnych przykładów startowych:

1. **Hello Agent** — tworzenie i wywoływanie podstawowego agenta
2. **Dodawanie narzędzi** — wyposażanie agenta w lokalne funkcje
3. **Rozmowy wieloturowe** — zachowanie kontekstu między wiadomościami
4. **Pamięć agenta** — niestandardowy `AIContextProvider` dla trwałego stanu
5. **Twój pierwszy przepływ pracy** — executory i krawędzie
6. **Hostowanie agenta** — Azure Functions z DurableAgents

Każdy rozdział prezentuje kompletny, uruchamialny `Program.cs` z odpowiedniego przykładu, a następnie wyjaśnia poszczególne elementy.

## Kod źródłowy

Wszystkie przykłady znajdują się w katalogu `dotnet/samples/01-get-started/` tego repozytorium.
