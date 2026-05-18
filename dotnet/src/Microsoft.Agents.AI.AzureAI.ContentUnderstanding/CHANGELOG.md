# Release History

## [Unreleased]

Initial public release ([#TBD](https://github.com/microsoft/agent-framework/pull/TBD)).

- Added `ContentUnderstandingContextProvider`, an `AIContextProvider` that runs PDF / image / audio / video attachments through Azure AI Content Understanding and injects the structured analysis (markdown, fields, segments) into the LLM input.
- Added `ContentUnderstandingContextProviderOptions` (analyzer id, `MaxWait` inline-vs-background threshold, output-section bitfield, optional file-search routing).
- Added `FileSearchConfig` with `FromFoundry` and `FromOpenAI` factories that wire a Foundry `AIProjectClient` or `OpenAIClient` vector store + caller-supplied `file_search` tool for over-budget analyses.
- 1:1 port of the Python `agent-framework-azure-contentunderstanding` package introduced in [microsoft/agent-framework#4829](https://github.com/microsoft/agent-framework/pull/4829). Eight end-to-end samples (single-turn QA, multi-turn session, multimodal chat, invoice processing, large-doc file-search, and three DevUI-hosted variants) under [`dotnet/samples/02-agents/AgentWithContentUnderstanding/`](https://github.com/microsoft/agent-framework/tree/main/dotnet/samples/02-agents/AgentWithContentUnderstanding). 130 unit tests + 4 live integration tests carrying `// parity: python tests/cu/<file>::<class>::<test>` annotations.

