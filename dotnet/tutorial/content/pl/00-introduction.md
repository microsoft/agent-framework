# Wprowadzenie do Microsoft Agent Framework

**Microsoft Agent Framework (MAF)** to biblioteka .NET do budowania agentów AI — autonomicznych programów, które rozumują, pamiętają i działają przy użyciu dużych modeli językowych.

MAF zapewnia przejrzyste, kompozycyjne API zbudowane na bazie `Microsoft.Extensions.AI`, ułatwiając:

- Tworzenie agentów obsługiwanych przez dowolnego dostawcę LLM (Azure OpenAI, OpenAI i inne)
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
- Zasób Azure OpenAI (lub klucz API OpenAI)
- Dwie zmienne środowiskowe:

```bash
export AZURE_OPENAI_ENDPOINT="https://twoj-zasob.openai.azure.com/"
export AZURE_OPENAI_DEPLOYMENT_NAME="gpt-4o-mini"
```

### Twój pierwszy agent (5 linii)

```csharp
using Azure.AI.OpenAI;
using Azure.Identity;
using Microsoft.Agents.AI;
using OpenAI.Chat;

AIAgent agent = new AzureOpenAIClient(
    new Uri(Environment.GetEnvironmentVariable("AZURE_OPENAI_ENDPOINT")!),
    new DefaultAzureCredential())
    .GetChatClient("gpt-4o-mini")
    .AsAIAgent(instructions: "Jesteś pomocnym asystentem.");

Console.WriteLine(await agent.RunAsync("Cześć!"));
```

Kluczową metodą rozszerzającą jest `.AsAIAgent()` — opakowuje dowolny `IChatClient` w pełnoprawny obiekt `AIAgent`.

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
