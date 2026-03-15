# Twój pierwszy przepływ pracy

**Przykład:** `dotnet/samples/01-get-started/05_first_workflow/`

Przepływy pracy pozwalają łączyć wiele jednostek przetwarzania (executorów) w skierowany graf. Dane przepływają przez krawędzie od jednego executora do następnego.

## Kompletny program

```csharp
// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.AI.Workflows;

namespace WorkflowExecutorsAndEdgesSample;

/// <summary>
/// Ten przykład wprowadza koncepcje executorów i krawędzi w przepływie pracy.
///
/// Przepływy pracy są zbudowane z executorów (jednostek przetwarzania) połączonych
/// krawędziami (ścieżkami przepływu danych). W tym przykładzie tworzymy prosty potok
/// przetwarzania tekstu, który:
/// 1. Pobiera tekst wejściowy i konwertuje go na wielkie litery (UppercaseExecutor)
/// 2. Pobiera tekst wielkich liter i odwraca go (ReverseTextExecutor)
///
/// Dla wejścia "Witaj, Świecie!" przepływ pracy produkuje "!EICŚIW ,JATIW".
/// </summary>
public static class Program
{
    private static async Task Main()
    {
        // Utwórz executory
        Func<string, string> uppercaseFunc = s => s.ToUpperInvariant();
        var uppercase = uppercaseFunc.BindAsExecutor("UppercaseExecutor");

        ReverseTextExecutor reverse = new();

        // Zbuduj przepływ pracy, łącząc executory sekwencyjnie
        WorkflowBuilder builder = new(uppercase);
        builder.AddEdge(uppercase, reverse).WithOutputFrom(reverse);
        var workflow = builder.Build();

        // Wykonaj przepływ pracy z danymi wejściowymi
        await using Run run = await InProcessExecution.RunAsync(workflow, "Witaj, Świecie!");
        foreach (WorkflowEvent evt in run.NewEvents)
        {
            if (evt is ExecutorCompletedEvent executorComplete)
            {
                Console.WriteLine($"{executorComplete.ExecutorId}: {executorComplete.Data}");
            }
        }
    }
}

/// <summary>
/// Drugi executor: odwraca tekst wejściowy i kończy przepływ pracy.
/// </summary>
internal sealed class ReverseTextExecutor() : Executor<string, string>("ReverseTextExecutor")
{
    public override ValueTask<string> HandleAsync(
        string message,
        IWorkflowContext context,
        CancellationToken cancellationToken = default)
    {
        return ValueTask.FromResult(string.Concat(message.Reverse()));
    }
}
```

**Wynik:**
```
UppercaseExecutor: WITAJ, ŚWIECIE!
ReverseTextExecutor: !EICŚIW ,JATIW
```

## Podstawowe koncepcje

### Executor

Executor to jednostka przetwarzania — węzeł w grafie przepływu pracy. Każdy executor:

- Ma **nazwę** (używaną w zdarzeniach i routingu)
- Przyjmuje silnie typowane **dane wejściowe** i produkuje silnie typowane **dane wyjściowe**
- Otrzymuje `IWorkflowContext` do dostępu do usług i dodawania niestandardowych zdarzeń

Dwa sposoby tworzenia executorów:

**1. Powiązanie z lambdą (dla prostych przypadków):**
```csharp
Func<string, string> uppercaseFunc = s => s.ToUpperInvariant();
var uppercase = uppercaseFunc.BindAsExecutor("UppercaseExecutor");
```

**2. Podklasa `Executor<TInput, TOutput>` (dla złożonej logiki):**
```csharp
internal sealed class ReverseTextExecutor() : Executor<string, string>("ReverseTextExecutor")
{
    public override ValueTask<string> HandleAsync(string message, IWorkflowContext context, CancellationToken cancellationToken = default)
    {
        return ValueTask.FromResult(string.Concat(message.Reverse()));
    }
}
```

### Krawędź

Krawędź łączy wyjście jednego executora z wejściem innego:

```csharp
builder.AddEdge(uppercase, reverse).WithOutputFrom(reverse);
```

- `AddEdge(from, to)` — dane przepływają z `uppercase` do `reverse`
- `.WithOutputFrom(reverse)` — oznacza `reverse` jako węzeł wyjściowy przepływu pracy

### WorkflowBuilder

```csharp
WorkflowBuilder builder = new(uppercase); // pierwszy executor = punkt wejścia
builder.AddEdge(uppercase, reverse).WithOutputFrom(reverse);
var workflow = builder.Build();
```

Konstruktor przyjmuje executor wejściowy. Dodaj krawędzie, aby połączyć kolejne executory. Wywołaj `Build()`, aby uzyskać niezmienialny `Workflow`.

### Run i zdarzenia

```csharp
await using Run run = await InProcessExecution.RunAsync(workflow, "Witaj, Świecie!");
foreach (WorkflowEvent evt in run.NewEvents)
{
    if (evt is ExecutorCompletedEvent executorComplete)
    {
        Console.WriteLine($"{executorComplete.ExecutorId}: {executorComplete.Data}");
    }
}
```

`InProcessExecution.RunAsync` wykonuje przepływ pracy w procesie. Obiekt `Run` udostępnia strumień zdarzeń `WorkflowEvent`. Dopasowuj wzorce do typów zdarzeń:

| Typ zdarzenia | Kiedy wystrzeliwuje |
|---|---|
| `ExecutorCompletedEvent` | Executor kończy działanie i produkuje dane wyjściowe |
| `WorkflowCompletedEvent` | Cały przepływ pracy kończy działanie |
| `SuperStepStartedEvent` | Rozpoczyna się nowa runda aktywacji executorów |

## Wzorce przepływów pracy

Poza prostym sekwencyjnym potokiem z tego przykładu, przepływy pracy obsługują:

- **Fan-out** — wyjście jednego executora zasila kilka executorów równolegle
- **Fan-in** — wyjścia kilku executorów zasilają jeden executor
- **Warunkowy routing** — executory mogą sprawdzać kontekst i wybierać, które krawędzie wyjściowe aktywować
- **Agenty AI jako executory** — `ChatClientAgent` może być powiązany jako executor

## Uruchamianie przykładu

```bash
cd dotnet/samples/01-get-started/05_first_workflow
dotnet run
```

## Kluczowe wnioski

- Executory to silnie typowane węzły przetwarzania
- `BindAsExecutor` opakowuje lambdę; utwórz podklasę `Executor<TIn, TOut>` dla złożonej logiki
- `WorkflowBuilder` łączy executory krawędziami
- `InProcessExecution.RunAsync` uruchamia przepływ pracy i zwraca `Run` ze strumieniem zdarzeń
- `ExecutorCompletedEvent` zawiera identyfikator executora i dane wyjściowe
