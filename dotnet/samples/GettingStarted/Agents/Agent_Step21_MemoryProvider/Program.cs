// Copyright (c) Microsoft. All rights reserved.

// This sample shows how to use an AIContextProvider as a persistent memory system for a ChatClientAgent.
// The NovelContextMemory provider extracts structured novel context (title, genre, setting, characters, outline, etc.)
// from each conversation turn and injects it back as additional AI context on subsequent turns.
// This gives the agent persistent, structured memory across the entire conversation.
// The provider extends AIContextProvider<TState> which provides built-in state management via the session's StateBag.

using System.Text;
using System.Text.Json;
using Azure.AI.OpenAI;
using Azure.Identity;
using Microsoft.Agents.AI;
using Microsoft.Extensions.AI;
using SampleApp;

var endpoint = Environment.GetEnvironmentVariable("AZURE_OPENAI_ENDPOINT") ?? throw new InvalidOperationException("AZURE_OPENAI_ENDPOINT is not set.");
var deploymentName = Environment.GetEnvironmentVariable("AZURE_OPENAI_DEPLOYMENT_NAME") ?? "gpt-4o-mini";

Console.OutputEncoding = Encoding.UTF8;

// Create an IChatClient that we'll use both for the agent and for the memory extraction calls.
// WARNING: DefaultAzureCredential is convenient for development but requires careful consideration in production.
// In production, consider using a specific credential (e.g., ManagedIdentityCredential) to avoid
// latency issues, unintended credential probing, and potential security risks from fallback mechanisms.
IChatClient chatClient = new AzureOpenAIClient(
    new Uri(endpoint),
    new DefaultAzureCredential())
    .GetChatClient(deploymentName)
    .AsIChatClient();

// Create the novel memory provider. It uses AIContextProvider<NovelContext> to persist structured
// novel facts in the session's StateBag automatically across turns.
var novelMemory = new NovelContextMemory(chatClient);

// Create agent with novel memory attached as an AI context provider.
AIAgent agent = new ChatClientAgent(chatClient, new ChatClientAgentOptions
{
    Name = NovelInstructions.AgentName,
    ChatOptions = new() { Instructions = NovelInstructions.Compose(NovelInstructions.WithNovelContext) },
    AIContextProviders = [novelMemory],
});

// Create session and start interactive chat loop.
AgentSession session = await agent.CreateSessionAsync();

Console.WriteLine("Novel Seed Architect (with memory)");
Console.WriteLine("Commands: /ctx (show memory), /exit\n");

bool serializedOnce = false;

while (true)
{
    Console.Write("You: ");
    var input = Console.ReadLine();
    if (string.IsNullOrWhiteSpace(input)) continue;
    if (input.Equals("/exit", StringComparison.OrdinalIgnoreCase)) break;

    // Show current memory state on demand.
    if (input.Equals("/ctx", StringComparison.OrdinalIgnoreCase))
    {
        var ctx = session.StateBag.GetValue<NovelContext>(nameof(NovelContextMemory));
        Console.WriteLine(ctx?.ToPrettyString() ?? "(empty)");
        continue;
    }

    // Stream the agent's response.
    Console.Write("Agent: ");
    await foreach (var update in agent.RunStreamingAsync(input, session))
    {
        if (!string.IsNullOrEmpty(update.Text))
            Console.Write(update.Text);
    }
    Console.WriteLine("\n");

    // Print memory after each turn so we can see what was extracted.
    PrintMemory(session);

    // After the first turn, demonstrate that NovelContext state survives session serialization.
    if (!serializedOnce)
    {
        serializedOnce = true;
        Console.WriteLine("[Demo] Verifying session serialization roundtrip...");
        var serialized = await agent.SerializeSessionAsync(session);
        session = await agent.DeserializeSessionAsync(serialized);
        var restored = session.StateBag.GetValue<NovelContext>(nameof(NovelContextMemory));
        Console.WriteLine($"[Demo] Roundtrip OK — Title after restore: {restored?.Title ?? "(null)"}\n");
    }
}

static void PrintMemory(AgentSession session)
{
    var ctx = session.StateBag.GetValue<NovelContext>(nameof(NovelContextMemory));
    Console.WriteLine("===========================================");
    Console.WriteLine(ctx?.ToPrettyString() ?? "(empty)");
    if (ctx?.OutlineSource is not null)
        Console.WriteLine($"  Outline source: ({ctx.OutlineSource})");
    Console.WriteLine("===========================================\n");
}

namespace SampleApp
{
    /// <summary>
    /// Agent instructions for the Novel Seed Architect.
    /// </summary>
    internal static class NovelInstructions
    {
        public const string AgentName = "NovelSeedArchitect";

        public const string CoreInstructions = """
            You are the Novel Seed Architect — an expert storytelling consultant who
            transforms rough novel ideas into structured novel outlines.

            When given a novel idea, produce this format:

            ## Novel Outline

            ### Title
            [Working title for the novel]

            ### Genre
            [Primary genre and subgenres]

            ### Setting
            [Time period, world, locations — the stage where the story unfolds]

            ### Protagonist
            [Name, background, motivation, internal conflict]

            ### Antagonist
            [Name or force, nature, motivation, relationship to protagonist]

            ### Theme
            [Central theme and underlying message]

            ### Synopsis
            [Two to three paragraphs describing the arc — setup, confrontation, resolution]

            ### Key Plot Points
            - [ ] Inciting incident
            - [ ] First turning point
            - [ ] Midpoint reversal
            - [ ] Crisis / dark moment
            - [ ] Climax
            - [ ] Resolution

            Be vivid but concise. Always produce consistent, well-formatted output.
            """;

        public const string WithNovelContext = """

            Important — Novel Memory:
            - You have persistent memory. Novel facts (title, genre, setting, protagonist,
              antagonist, theme) are accumulated across turns. Use them to ground every response.
            - If key novel context is missing (see the "Missing context" section), proactively
              ask 1-2 targeted questions to fill those gaps. Weave the questions naturally into
              your response — for example: "Before I flesh out the antagonist, what genre are
              you aiming for?" Do NOT wait for the user to volunteer this information.
            - If a Novel Outline is present, treat it as work-in-progress.
              Refine and improve it with each turn rather than starting from scratch.
              Add sections that are missing, sharpen existing ones, incorporate new details.
            - When you produce or update a novel outline, always output the full current
              version so memory can capture it — even if some sections are still incomplete.

            CRITICAL — Novel Outline Delimiters:
            Whenever you output a novel outline (full or partial), you MUST wrap it
            in these exact delimiter lines:
            <<<NOVEL_OUTLINE>>>
            (your full novel outline here)
            <<<END_NOVEL_OUTLINE>>>
            These delimiters are used by the memory system to capture and persist the outline.
            Always include them — even when the outline is a rough draft or work-in-progress.
            You may include additional commentary, questions, or analysis OUTSIDE the delimiters.
            """;

        public static string Compose(params string[] additions)
            => string.Concat(CoreInstructions, string.Concat(additions));
    }

    /// <summary>
    /// Structured record representing the current novel context (title, genre, characters, outline, etc.).
    /// </summary>
    internal sealed record NovelContext(
        string? Title,
        string? Genre,
        string? Setting,
        string? Protagonist,
        string? Antagonist,
        string? Theme,
        string? Outline,
        string? OutlineSource)
    {
        public static NovelContext Empty => new(null, null, null, null, null, null, null, null);

        public string ToPrettyString()
        {
            var sb = new StringBuilder();
            sb.AppendLine($"  Title:        {this.Title ?? "(unknown)"}");
            sb.AppendLine($"  Genre:        {this.Genre ?? "(unknown)"}");
            sb.AppendLine($"  Setting:      {this.Setting ?? "(unknown)"}");
            sb.AppendLine($"  Protagonist:  {this.Protagonist ?? "(unknown)"}");
            sb.AppendLine($"  Antagonist:   {this.Antagonist ?? "(unknown)"}");
            sb.AppendLine($"  Theme:        {this.Theme ?? "(unknown)"}");
            if (this.Outline is not null)
            {
                var lines = this.Outline.Split('\n')
                    .Where(l => !string.IsNullOrWhiteSpace(l))
                    .Select(l => l.TrimStart('#', ' ', '-', '[', ']', '*'))
                    .Where(l => l.Length > 0)
                    .Take(6)
                    .ToList();
                sb.AppendLine($"  Outline:      {lines.FirstOrDefault() ?? "(untitled)"}");
                foreach (var line in lines.Skip(1))
                    sb.AppendLine($"                {line}");
            }
            else
            {
                sb.AppendLine("  Outline:      (none yet)");
            }
            return sb.ToString();
        }
    }

    /// <summary>
    /// Delta record used for structured extraction from LLM responses.
    /// Internal (not public) because it is only used by <see cref="NovelContextMemory"/> for JSON deserialization.
    /// </summary>
    [System.Diagnostics.CodeAnalysis.SuppressMessage("Performance", "CA1812:Avoid uninstantiated internal classes", Justification = "Instantiated by JSON deserialization.")]
    internal sealed record NovelContextDelta(
        string? Title, string? Genre, string? Setting,
        string? Protagonist, string? Antagonist, string? Theme,
        string? Outline);

    /// <summary>
    /// An <see cref="AIContextProvider"/> that acts as persistent memory for a novel-writing agent.
    /// On each turn it injects the current novel context as additional instructions, and after each
    /// turn it extracts structured novel facts from the conversation to update the context.
    /// </summary>
    internal sealed class NovelContextMemory : AIContextProvider<NovelContext>
    {
        private readonly IChatClient _chatClient;

        public NovelContextMemory(IChatClient chatClient)
            : base(
                stateInitializer: _ => NovelContext.Empty,
                stateKey: null,
                jsonSerializerOptions: null,
                provideInputMessageFilter: null,
                storeInputMessageFilter: null)
        {
            this._chatClient = chatClient;
        }

        protected override ValueTask<AIContext> ProvideAIContextAsync(InvokingContext context, CancellationToken cancellationToken = default)
        {
            var state = this.GetOrInitializeState(context.Session);

            var sb = new StringBuilder();
            sb.AppendLine("## Novel Context (authoritative)");
            if (!string.IsNullOrWhiteSpace(state.Title))        sb.AppendLine($"- Title: {state.Title}");
            if (!string.IsNullOrWhiteSpace(state.Genre))         sb.AppendLine($"- Genre: {state.Genre}");
            if (!string.IsNullOrWhiteSpace(state.Setting))       sb.AppendLine($"- Setting: {state.Setting}");
            if (!string.IsNullOrWhiteSpace(state.Protagonist))   sb.AppendLine($"- Protagonist: {state.Protagonist}");
            if (!string.IsNullOrWhiteSpace(state.Antagonist))    sb.AppendLine($"- Antagonist: {state.Antagonist}");
            if (!string.IsNullOrWhiteSpace(state.Theme))         sb.AppendLine($"- Theme: {state.Theme}");
            if (state.Outline is not null)
            {
                sb.AppendLine();
                sb.AppendLine("## Novel Outline (work-in-progress)");
                sb.AppendLine(state.Outline);
            }

            var missing = new List<string>();
            if (string.IsNullOrWhiteSpace(state.Title))        missing.Add("Title");
            if (string.IsNullOrWhiteSpace(state.Genre))         missing.Add("Genre");
            if (string.IsNullOrWhiteSpace(state.Setting))       missing.Add("Setting");
            if (string.IsNullOrWhiteSpace(state.Protagonist))   missing.Add("Protagonist");
            if (string.IsNullOrWhiteSpace(state.Antagonist))    missing.Add("Antagonist");
            if (string.IsNullOrWhiteSpace(state.Theme))         missing.Add("Theme");
            if (state.Outline is null)                           missing.Add("Outline");

            if (missing.Count > 0)
            {
                sb.AppendLine();
                sb.AppendLine($"## Missing context — ask the user about: {string.Join(", ", missing)}");
            }

            return new ValueTask<AIContext>(new AIContext { Instructions = sb.ToString() });
        }

        private const string OutlineStart = "<<<NOVEL_OUTLINE>>>";
        private const string OutlineEnd   = "<<<END_NOVEL_OUTLINE>>>";

        protected override async ValueTask StoreAIContextAsync(InvokedContext context, CancellationToken cancellationToken = default)
        {
            if (!context.RequestMessages.Any(m => m.Role == ChatRole.User)) return;

            var state = this.GetOrInitializeState(context.Session);
            var responseMessages = (context.ResponseMessages ?? []).ToList();
            var allMessages = context.RequestMessages.Concat(responseMessages).ToList();

            var currentOutline = state.Outline;

            const string outlineInstruction = """

                    ## Outline — Extract or update the novel outline:
                    Outline is a multiline string field containing the full novel outline.
                    The ASSISTANT's response may contain a novel outline wrapped between
                    <<<NOVEL_OUTLINE>>> and <<<END_NOVEL_OUTLINE>>> delimiters.
                    If those delimiters are present, copy ALL the content between them (excluding the
                    delimiter lines themselves) verbatim into Outline.
                    Preserve the full markdown content exactly as-is — do not summarize or truncate.
                    If the delimiters are NOT present in this turn, set Outline to null.
                    IMPORTANT: DO NOT INCLUDE THE DELIMITER LINES THEMSELVES.
                    """;

            NovelContextDelta delta;
            try
            {
                var extraction = await this._chatClient.GetResponseAsync<NovelContextDelta>(
                    allMessages,
                    new ChatOptions
                    {
                        Instructions = $"""
                            You are a precise information extraction assistant.
                            Extract structured data from the conversation messages.

                            ## Novel Facts (from USER messages):
                            - Title: the working title of the novel (null if not mentioned by the user)
                            - Genre: genre and subgenres mentioned (null if not mentioned by the user)
                            - Setting: time period, world, locations (null if not mentioned by the user)
                            - Protagonist: name, traits, motivation (null if not mentioned by the user)
                            - Antagonist: name or force, nature, motivation (null if not mentioned by the user)
                            - Theme: central theme or message (null if not mentioned by the user)
                            For the six fields above, return null if not mentioned.
                            Do NOT apply this null rule to Outline — that field has its own rules below.
                            {outlineInstruction}
                            """
                    },
                    cancellationToken: cancellationToken);

                delta = extraction.Result;
            }
            catch (Exception ex) when (ex is not OperationCanceledException)
            {
                // LLM extraction failed — fall back to delimiter parsing only.
                // Memory update is best-effort; failures should not break the agent interaction.
                Console.WriteLine($"[NovelContextMemory] Extraction failed, falling back to delimiter parsing: {ex.Message}");
                delta = new NovelContextDelta(null, null, null, null, null, null, null);
            }

            // Outline extraction uses a two-phase strategy:
            // 1. Primary: the LLM structured extraction (above) should capture the outline.
            // 2. Fallback: if the LLM missed it, parse the raw response for <<<NOVEL_OUTLINE>>> delimiters.
            // This ensures the outline is captured even when the LLM's structured output omits it.
            var llmOutlineFound = !string.IsNullOrWhiteSpace(delta.Outline);

            string? outlineToStore;
            string? outlineSource = null;
            if (llmOutlineFound)
            {
                outlineToStore = delta.Outline;
                outlineSource = "llm";
            }
            else
            {
                // Fallback: parse delimiters directly from the assistant's response text.
                var delimiterOutline = ExtractOutlineBetweenDelimiters(responseMessages);
                if (delimiterOutline is not null)
                {
                    outlineToStore = delimiterOutline;
                    outlineSource = "delimiter";
                }
                else
                {
                    outlineToStore = currentOutline;
                    outlineSource = state.OutlineSource;
                }
            }

            // Set the resolved outline on the delta so Merge() handles all fields uniformly.
            delta = delta with { Outline = outlineToStore };
            var newState = Merge(state, delta) with { OutlineSource = outlineSource };
            _sessionState.SaveState(context.Session, newState);
        }

        private static string? ExtractOutlineBetweenDelimiters(IEnumerable<ChatMessage> messages)
        {
            var lastAssistant = messages.LastOrDefault(m => m.Role == ChatRole.Assistant);
            if (lastAssistant is null) return null;

            var text = lastAssistant.Text;
            if (string.IsNullOrWhiteSpace(text)) return null;

            var startIdx = text.IndexOf(OutlineStart, StringComparison.Ordinal);
            if (startIdx < 0) return null;

            var contentStart = startIdx + OutlineStart.Length;
            var endIdx = text.IndexOf(OutlineEnd, contentStart, StringComparison.Ordinal);

            var content = endIdx >= 0
                ? text[contentStart..endIdx]
                : text[contentStart..];

            var trimmed = content.Trim();
            return trimmed.Length > 0 ? trimmed : null;
        }

        private static NovelContext Merge(NovelContext current, NovelContextDelta delta)
        {
            return current with
            {
                Title       = delta.Title ?? current.Title,
                Genre       = delta.Genre ?? current.Genre,
                Setting     = delta.Setting ?? current.Setting,
                Protagonist = delta.Protagonist ?? current.Protagonist,
                Antagonist  = delta.Antagonist ?? current.Antagonist,
                Theme       = delta.Theme ?? current.Theme,
                Outline     = delta.Outline ?? current.Outline
            };
        }
    }
}
