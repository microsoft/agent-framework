# Harness "Pipeline"
Focused on answering the question: What's in the pipeline with regards to the _Dev Harness_?

## Features

1. Slot Filling Orchestration (a.k.a. "Guided Conversations")
   
2. Functional Compaction Strategy

Support a functional pattern for creating a compaction strategy with a range of configurations:

```c#
// Setup a chat client for summarization
IChatClient summarizingChatClient = ...;

// Create a compaction strategy based on a menu selection of characteristics
CompactionStrategy tunedStrategy =
   CompactionStrategy.Create(
      Approach.Balanced,
      Size.Compact,
      summarizingChatClient);
```

As an alternative to making every configuration decision:

```c#
// Setup a chat client for summarization
IChatClient summarizingChatClient = ...;

// Configure the compaction pipeline with one of each strategy, ordered least to most aggressive.
PipelineCompactionStrategy compactionPipeline =
    new(// 1. Gentle: collapse old tool-call groups into short summaries like "[Tool calls: LookupPrice]"
        new ToolResultCompactionStrategy(CompactionTriggers.TokensExceed(0x200)),

        // 2. Moderate: use an LLM to summarize older conversation spans into a concise message
        new SummarizationCompactionStrategy(summarizingChatClient, CompactionTriggers.TokensExceed(0x500)),

        // 3. Aggressive: keep only the last N user turns and their responses
        new SlidingWindowCompactionStrategy(CompactionTriggers.TurnsExceed(4)),

        // 4. Emergency: drop oldest groups until under the token budget
        new TruncationCompactionStrategy(CompactionTriggers.TokensExceed(0x8000)));
```

3. Test Framework: Large Context

4. Stabilization
