# Changelog

All notable changes to the Agent Framework Python packages will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [1.0.0b260130] - 2026-01-30

### Added

- **agent-framework-claude**: Add BaseAgent implementation for Claude Agent SDK ([#3509](https://github.com/microsoft/agent-framework/pull/3509))
- **agent-framework-core**: Add core types and agents unit tests ([#3470](https://github.com/microsoft/agent-framework/pull/3470))
- **agent-framework-core**: Add core utilities unit tests ([#3487](https://github.com/microsoft/agent-framework/pull/3487))
- **agent-framework-core**: Add observability unit tests to improve coverage ([#3469](https://github.com/microsoft/agent-framework/pull/3469))
- **agent-framework-azure-ai**: Improved AzureAI package test coverage ([#3452](https://github.com/microsoft/agent-framework/pull/3452))

### Changed

- **agent-framework-core**: Added generic types to `ChatOptions` and `ChatResponse`/`AgentResponse` for Response Format ([#3305](https://github.com/microsoft/agent-framework/pull/3305))
- **agent-framework-durabletask**: Update durabletask package ([#3492](https://github.com/microsoft/agent-framework/pull/3492))

## [1.0.0b260128] - 2026-01-28

### Changed

- **agent-framework-core**: [BREAKING] Renamed `@ai_function` decorator to `@tool` and `AIFunction` to `FunctionTool` ([#3413](https://github.com/microsoft/agent-framework/pull/3413))
- **agent-framework-core**: [BREAKING] Add factory pattern to `GroupChatBuilder` and `MagenticBuilder` ([#3224](https://github.com/microsoft/agent-framework/pull/3224))
- **agent-framework-github-copilot**: [BREAKING] Renamed `Github` to `GitHub`  ([#3486](https://github.com/microsoft/agent-framework/pull/3486))

## [1.0.0b260127] - 2026-01-27

### Added

- **agent-framework-github-copilot**: Add BaseAgent implementation for GitHub Copilot SDK ([#3404](https://github.com/microsoft/agent-framework/pull/3404))

## [1.0.0b260123] - 2026-01-23

### Added

- **agent-framework-azure-ai**: Add support for `rai_config` in agent creation ([#3265](https://github.com/microsoft/agent-framework/pull/3265))
- **agent-framework-azure-ai**: Support reasoning config for `AzureAIClient` ([#3403](https://github.com/microsoft/agent-framework/pull/3403))
- **agent-framework-anthropic**: Add `response_format` support for structured outputs ([#3301](https://github.com/microsoft/agent-framework/pull/3301))

### Changed

- **agent-framework-core**: [BREAKING] Simplify content types to a single class with classmethod constructors ([#3252](https://github.com/microsoft/agent-framework/pull/3252))
- **agent-framework-core**: [BREAKING] Make `response_format` validation errors visible to users ([#3274](https://github.com/microsoft/agent-framework/pull/3274))
- **agent-framework-ag-ui**: [BREAKING] Simplify run logic; fix MCP and Anthropic client issues ([#3322](https://github.com/microsoft/agent-framework/pull/3322))
- **agent-framework-core**: Prefer runtime `kwargs` for `conversation_id` in OpenAI Responses client ([#3312](https://github.com/microsoft/agent-framework/pull/3312))

### Fixed

- **agent-framework-core**: Verify types during checkpoint deserialization to prevent marker spoofing ([#3243](https://github.com/microsoft/agent-framework/pull/3243))
- **agent-framework-core**: Filter internal args when passing kwargs to MCP tools ([#3292](https://github.com/microsoft/agent-framework/pull/3292))
- **agent-framework-core**: Handle anyio cancel scope errors during MCP connection cleanup ([#3277](https://github.com/microsoft/agent-framework/pull/3277))
- **agent-framework-core**: Filter `conversation_id` when passing kwargs to agent as tool ([#3266](https://github.com/microsoft/agent-framework/pull/3266))
- **agent-framework-core**: Fix `use_agent_middleware` calling private `_normalize_messages` ([#3264](https://github.com/microsoft/agent-framework/pull/3264))
- **agent-framework-core**: Add `system_instructions` to ChatClient LLM span tracing ([#3164](https://github.com/microsoft/agent-framework/pull/3164))
- **agent-framework-core**: Fix Azure chat client asynchronous filtering ([#3260](https://github.com/microsoft/agent-framework/pull/3260))
- **agent-framework-core**: Fix `HostedImageGenerationTool` mapping to `ImageGenTool` for Azure AI ([#3263](https://github.com/microsoft/agent-framework/pull/3263))
- **agent-framework-azure-ai**: Fix local MCP tools with `AzureAIProjectAgentProvider` ([#3315](https://github.com/microsoft/agent-framework/pull/3315))
- **agent-framework-azurefunctions**: Fix MCP tool invocation to use the correct agent ([#3339](https://github.com/microsoft/agent-framework/pull/3339))
- **agent-framework-declarative**: Fix MCP tool connection not passed from YAML to Azure AI agent creation API ([#3248](https://github.com/microsoft/agent-framework/pull/3248))
- **agent-framework-ag-ui**: Properly handle JSON serialization with handoff workflows as agent ([#3275](https://github.com/microsoft/agent-framework/pull/3275))
- **agent-framework-devui**: Ensure proper form rendering for `int` ([#3201](https://github.com/microsoft/agent-framework/pull/3201))

## [1.0.0b260116] - 2026-01-16

### Added

- **agent-framework-azure-ai**: Create/Get Agent API for Azure V1 ([#3192](https://github.com/microsoft/agent-framework/pull/3192))
- **agent-framework-core**: Create/Get Agent API for OpenAI Assistants ([#3208](https://github.com/microsoft/agent-framework/pull/3208))
- **agent-framework-ag-ui**: Support service-managed thread on AG-UI ([#3136](https://github.com/microsoft/agent-framework/pull/3136))
- **agent-framework-ag-ui**: Add MCP tool support for AG-UI approval flows ([#3212](https://github.com/microsoft/agent-framework/pull/3212))
- **samples**: Add AzureAI sample for downloading code interpreter generated files ([#3189](https://github.com/microsoft/agent-framework/pull/3189))

### Changed

- **agent-framework-core**: [BREAKING] Rename `create_agent` to `as_agent` ([#3249](https://github.com/microsoft/agent-framework/pull/3249))
- **agent-framework-core**: [BREAKING] Rename `WorkflowOutputEvent.source_executor_id` to `executor_id` for API consistency ([#3166](https://github.com/microsoft/agent-framework/pull/3166))

### Fixed

- **agent-framework-core**: Properly configure structured outputs based on new options dict ([#3213](https://github.com/microsoft/agent-framework/pull/3213))
- **agent-framework-core**: Correct `FunctionResultContent` ordering in `WorkflowAgent.merge_updates` ([#3168](https://github.com/microsoft/agent-framework/pull/3168))
- **agent-framework-azurefunctions**: Update `DurableAIAgent` and fix integration tests ([#3241](https://github.com/microsoft/agent-framework/pull/3241))
- **agent-framework-azure-ai**: Create/Get Agent API fixes and example improvements ([#3246](https://github.com/microsoft/agent-framework/pull/3246))

## [1.0.0b260114] - 2026-01-14

### Added

- **agent-framework-azure-ai**: Create/Get Agent API for Azure V2 ([#3059](https://github.com/microsoft/agent-framework/pull/3059)) by @moonbox3
- **agent-framework-declarative**: Add declarative workflow runtime ([#2815](https://github.com/microsoft/agent-framework/pull/2815)) by @moonbox3
- **agent-framework-ag-ui**: Add dependencies param to ag-ui FastAPI endpoint ([#3191](https://github.com/microsoft/agent-framework/pull/3191)) by @moonbox3
- **agent-framework-ag-ui**: Add Pydantic request model and OpenAPI tags support to AG-UI FastAPI endpoint ([#2522](https://github.com/microsoft/agent-framework/pull/2522)) by @claude89757
- **agent-framework-core**: Add tool call/result content types and update connectors and samples ([#2971](https://github.com/microsoft/agent-framework/pull/2971)) by @moonbox3
- **agent-framework-core**: Add more specific exceptions to Workflow ([#3188](https://github.com/microsoft/agent-framework/pull/3188)) by @TaoChenOSU

### Changed

- **agent-framework-core**: [BREAKING] Refactor orchestrations ([#3023](https://github.com/microsoft/agent-framework/pull/3023)) by @TaoChenOSU
- **agent-framework-core**: [BREAKING] Introducing Options as TypedDict and Generic ([#3140](https://github.com/microsoft/agent-framework/pull/3140)) by @eavanvalkenburg
- **agent-framework-core**: [BREAKING] Removed display_name, renamed context_providers, middleware and AggregateContextProvider ([#3139](https://github.com/microsoft/agent-framework/pull/3139)) by @eavanvalkenburg
- **agent-framework-core**: MCP Improvements: improved connection loss behavior, pagination for loading and a param to control representation ([#3154](https://github.com/microsoft/agent-framework/pull/3154)) by @eavanvalkenburg
- **agent-framework-azure-ai**: Azure AI direct A2A endpoint support ([#3127](https://github.com/microsoft/agent-framework/pull/3127)) by @moonbox3

### Fixed

- **agent-framework-anthropic**: Fix duplicate ToolCallStartEvent in streaming tool calls ([#3051](https://github.com/microsoft/agent-framework/pull/3051)) by @moonbox3
- **agent-framework-anthropic**: Fix Anthropic streaming response bugs ([#3141](https://github.com/microsoft/agent-framework/pull/3141)) by @eavanvalkenburg
- **agent-framework-ag-ui**: Execute tools with approval_mode, fix shared state, code cleanup ([#3079](https://github.com/microsoft/agent-framework/pull/3079)) by @moonbox3
- **agent-framework-azure-ai**: Fix AzureAIClient tool call bug for AG-UI use ([#3148](https://github.com/microsoft/agent-framework/pull/3148)) by @moonbox3
- **agent-framework-core**: Fix MCPStreamableHTTPTool to use new streamable_http_client API ([#3088](https://github.com/microsoft/agent-framework/pull/3088)) by @Copilot
- **agent-framework-core**: Multiple bug fixes ([#3150](https://github.com/microsoft/agent-framework/pull/3150)) by @eavanvalkenburg

## [1.0.0b260107] - 2026-01-07

### Added

- **agent-framework-devui**: Improve DevUI and add Context Inspector view as a new tab under traces ([#2742](https://github.com/microsoft/agent-framework/pull/2742)) by @victordibia
- **samples**: Add streaming sample for Azure Functions ([#3057](https://github.com/microsoft/agent-framework/pull/3057)) by @gavin-aguiar

### Changed

- **repo**: Update templates ([#3106](https://github.com/microsoft/agent-framework/pull/3106)) by @eavanvalkenburg

### Fixed

- **agent-framework-ag-ui**: Fix MCP tool result serialization for list[TextContent] ([#2523](https://github.com/microsoft/agent-framework/pull/2523)) by @claude89757
- **agent-framework-azure-ai**: Fix response_format handling for structured outputs ([#3114](https://github.com/microsoft/agent-framework/pull/3114)) by @moonbox3

## [1.0.0b260106] - 2026-01-06

### Added

- **repo**: Add issue template and additional labeling ([#3006](https://github.com/microsoft/agent-framework/pull/3006)) by @eavanvalkenburg

### Changed

- None

### Fixed

- **agent-framework-core**: Fix max tokens translation and add extra integer test ([#3037](https://github.com/microsoft/agent-framework/pull/3037)) by @eavanvalkenburg
- **agent-framework-azure-ai**: Fix failure when conversation history contains assistant messages ([#3076](https://github.com/microsoft/agent-framework/pull/3076)) by @moonbox3
- **agent-framework-core**: Use HTTP exporter for http/protobuf protocol ([#3070](https://github.com/microsoft/agent-framework/pull/3070)) by @takanori-terai
- **agent-framework-core**: Fix ExecutorInvokedEvent and ExecutorCompletedEvent observability data ([#3090](https://github.com/microsoft/agent-framework/pull/3090)) by @moonbox3
- **agent-framework-core**: Honor tool_choice parameter passed to agent.run() and chat client methods ([#3095](https://github.com/microsoft/agent-framework/pull/3095)) by @moonbox3
- **samples**: AzureAI SharePoint sample fix ([#3108](https://github.com/microsoft/agent-framework/pull/3108)) by @giles17

## [1.0.0b251223] - 2025-12-23

### Added

- **agent-framework-bedrock**: Introducing support for Bedrock-hosted models (Anthropic, Cohere, etc.) ([#2610](https://github.com/microsoft/agent-framework/pull/2610))
- **agent-framework-core**: Added `response.created` and `response.in_progress` event process to `OpenAIBaseResponseClient` ([#2975](https://github.com/microsoft/agent-framework/pull/2975))
- **agent-framework-foundry-local**: Introducing Foundry Local Chat Clients ([#2915](https://github.com/microsoft/agent-framework/pull/2915))
- **samples**: Added GitHub MCP sample with PAT ([#2967](https://github.com/microsoft/agent-framework/pull/2967))

### Changed

- **agent-framework-core**: Preserve reasoning blocks with OpenRouter ([#2950](https://github.com/microsoft/agent-framework/pull/2950))

## [1.0.0b251218] - 2025-12-18

### Added

- **agent-framework-core**: Azure AI Agent with Bing Grounding Citations sample ([#2892](https://github.com/microsoft/agent-framework/pull/2892))
- **agent-framework-core**: Workflow option to visualize internal executors ([#2917](https://github.com/microsoft/agent-framework/pull/2917))
- **agent-framework-core**: Workflow cancellation sample ([#2732](https://github.com/microsoft/agent-framework/pull/2732))
- **agent-framework-core**: Azure Managed Redis support with credential provider ([#2887](https://github.com/microsoft/agent-framework/pull/2887))
- **agent-framework-core**: Additional arguments for Azure AI agent configuration ([#2922](https://github.com/microsoft/agent-framework/pull/2922))

### Changed

- **agent-framework-ollama**: Updated Ollama package version ([#2920](https://github.com/microsoft/agent-framework/pull/2920))
- **agent-framework-ollama**: Move Ollama samples to samples getting started directory ([#2921](https://github.com/microsoft/agent-framework/pull/2921))
- **agent-framework-core**: Cleanup and refactoring of chat clients ([#2937](https://github.com/microsoft/agent-framework/pull/2937))
- **agent-framework-core**: Align Run ID and Thread ID casing with AG-UI TypeScript SDK ([#2948](https://github.com/microsoft/agent-framework/pull/2948))

### Fixed

- **agent-framework-core**: Fix Pydantic error when using Literal types for tool parameters ([#2893](https://github.com/microsoft/agent-framework/pull/2893))
- **agent-framework-core**: Correct MCP image type conversion in `_mcp.py` ([#2901](https://github.com/microsoft/agent-framework/pull/2901))
- **agent-framework-core**: Fix BadRequestError when using Pydantic models in response formatting ([#1843](https://github.com/microsoft/agent-framework/pull/1843))
- **agent-framework-core**: Propagate workflow kwargs to sub-workflows via WorkflowExecutor ([#2923](https://github.com/microsoft/agent-framework/pull/2923))
- **agent-framework-core**: Fix WorkflowAgent event handling and kwargs forwarding ([#2946](https://github.com/microsoft/agent-framework/pull/2946))

## [1.0.0b251216] - 2025-12-16

### Added

- **agent-framework-ollama**: Ollama connector for Agent Framework (#1104)
- **agent-framework-core**: Added custom args and thread object to `ai_function` kwargs (#2769)
- **agent-framework-core**: Enable checkpointing for `WorkflowAgent` (#2774)

### Changed

- **agent-framework-core**: [BREAKING] Observability updates (#2782)
- **agent-framework-core**: Use agent description in `HandoffBuilder` auto-generated tools (#2714)
- **agent-framework-core**: Remove warnings from workflow builder when not using factories (#2808)

### Fixed

- **agent-framework-core**: Fix `WorkflowAgent` to include thread conversation history (#2774)
- **agent-framework-core**: Fix context duplication in handoff workflows when restoring from checkpoint (#2867)
- **agent-framework-core**: Fix middleware terminate flag to exit function calling loop immediately (#2868)
- **agent-framework-core**: Fix `WorkflowAgent` to emit `yield_output` as agent response (#2866)
- **agent-framework-core**: Filter framework kwargs from MCP tool invocations (#2870)

## [1.0.0b251211] - 2025-12-11

### Added

- **agent-framework-core**: Extend HITL support for all orchestration patterns (#2620)
- **agent-framework-core**: Add factory pattern to concurrent orchestration builder (#2738)
- **agent-framework-core**: Add factory pattern to sequential orchestration builder (#2710)
- **agent-framework-azure-ai**: Capture file IDs from code interpreter in streaming responses (#2741)

### Changed

- **agent-framework-azurefunctions**: Change DurableAIAgent log level from warning to debug when invoked without thread (#2736)

### Fixed

- **agent-framework-core**: Added more complete parsing for mcp tool arguments (#2756)
- **agent-framework-core**: Fix GroupChat ManagerSelectionResponse JSON Schema for OpenAI Structured Outputs (#2750)
- **samples**: Standardize OpenAI API key environment variable naming (#2629)

## [1.0.0b251209] - 2025-12-09

### Added

- **agent-framework-core**: Support an autonomous handoff flow (#2497)
- **agent-framework-core**: WorkflowBuilder registry (#2486)
- **agent-framework-a2a**: Add configurable timeout support to A2AAgent (#2432)
- **samples**: Added Azure OpenAI Responses File Search sample + Integration test update (#2645)
- **samples**: Update fan in fan out sample to show concurrency (#2705)

### Changed

- **agent-framework-azure-ai**: [BREAKING] Renamed `async_credential` to `credential` (#2648)
- **samples**: Improve sample logging (#2692)
- **samples**: azureai image gen sample update (#2709)

### Fixed

- **agent-framework-core**: Fix DurableState schema serializations (#2670)
- **agent-framework-core**: Fix context provider lifecycle agentic mode (#2650)
- **agent-framework-devui**: Fix WorkflowFailedEvent error extraction (#2706)
- **agent-framework-devui**: Fix DevUI fails when uploading Pdf file (#2675)
- **agent-framework-devui**: Fix message serialization issue (#2674)
- **observability**: Display system prompt in langfuse (#2653)

## [1.0.0b251204] - 2025-12-04

### Added

- **agent-framework-core**: Add support for Pydantic `BaseModel` as function call result (#2606)
- **agent-framework-core**: Executor events now include I/O data (#2591)
- **samples**: Inline YAML declarative sample (#2582)
- **samples**: Handoff-as-agent with HITL sample (#2534)

### Changed

- **agent-framework-core**: [BREAKING] Support Magentic agent tool call approvals and plan stalling HITL behavior (#2569)
- **agent-framework-core**: [BREAKING] Standardize orchestration outputs as list of `ChatMessage`; allow agent as group chat manager (#2291)
- **agent-framework-core**: [BREAKING] Respond with `AgentRunResponse` including serialized structured output (#2285)
- **observability**: Use `executor_id` and `edge_group_id` as span names for clearer traces (#2538)
- **agent-framework-devui**: Add multimodal input support for workflows and refactor chat input (#2593)
- **docs**: Update Python orchestration documentation (#2087)

### Fixed

- **observability**: Resolve mypy error in observability module (#2641)
- **agent-framework-core**: Fix `AgentRunResponse.created_at` returning local datetime labeled as UTC (#2590)
- **agent-framework-core**: Emit `ExecutorFailedEvent` before `WorkflowFailedEvent` when executor throws (#2537)
- **agent-framework-core**: Fix MagenticAgentExecutor producing `repr` string for tool call content (#2566)
- **agent-framework-core**: Fixed empty text content Pydantic validation failure (#2539)
- **agent-framework-azure-ai**: Added support for application endpoints in Azure AI client (#2460)
- **agent-framework-azurefunctions**: Add MCP tool support (#2385)
- **agent-framework-core**: Preserve MCP array items schema in Pydantic field generation (#2382)
- **agent-framework-devui**: Make tool call view optional and fix links (#2243)
- **agent-framework-core**: Always include output in function call result messages (#2414)
- **agent-framework-redis**: Fix TypeError (#2411)

## [1.0.0b251120] - 2025-11-20

### Added

- **agent-framework-core**: Introducing support for declarative YAML spec ([#2002](https://github.com/microsoft/agent-framework/pull/2002))
- **agent-framework-core**: Use AI Foundry evaluators for self-reflection ([#2250](https://github.com/microsoft/agent-framework/pull/2250))
- **agent-framework-core**: Propagate `as_tool()` kwargs and add runtime context + middleware sample ([#2311](https://github.com/microsoft/agent-framework/pull/2311))
- **agent-framework-anthropic**: Anthropic Foundry integration ([#2302](https://github.com/microsoft/agent-framework/pull/2302))
- **samples**: M365 Agent SDK Hosting sample ([#2292](https://github.com/microsoft/agent-framework/pull/2292))
- **samples**: Foundry Sample for A2A + SharePoint Samples ([#2313](https://github.com/microsoft/agent-framework/pull/2313))

### Changed

- **agent-framework-azurefunctions**: [BREAKING] Schema changes for Azure Functions package ([#2151](https://github.com/microsoft/agent-framework/pull/2151))
- **agent-framework-core**: Move evaluation folders under `evaluations` ([#2355](https://github.com/microsoft/agent-framework/pull/2355))
- **agent-framework-core**: Move red teaming files to their own folder ([#2333](https://github.com/microsoft/agent-framework/pull/2333))
- **agent-framework-core**: "fix all" task now single source of truth ([#2303](https://github.com/microsoft/agent-framework/pull/2303))
- **agent-framework-core**: Improve and clean up exception handling ([#2337](https://github.com/microsoft/agent-framework/pull/2337), [#2319](https://github.com/microsoft/agent-framework/pull/2319))
- **agent-framework-core**: Clean up imports ([#2318](https://github.com/microsoft/agent-framework/pull/2318))

### Fixed

- **agent-framework-azure-ai**: Fix for Azure AI client ([#2358](https://github.com/microsoft/agent-framework/pull/2358))
- **agent-framework-core**: Fix tool execution bleed-over in aiohttp/Bot Framework scenarios ([#2314](https://github.com/microsoft/agent-framework/pull/2314))
- **agent-framework-core**: `@ai_function` now correctly handles `self` parameter ([#2266](https://github.com/microsoft/agent-framework/pull/2266))
- **agent-framework-core**: Resolve string annotations in `FunctionExecutor` ([#2308](https://github.com/microsoft/agent-framework/pull/2308))
- **agent-framework-core**: Langfuse observability captures ChatAgent system instructions ([#2316](https://github.com/microsoft/agent-framework/pull/2316))
- **agent-framework-core**: Incomplete URL substring sanitization fix ([#2274](https://github.com/microsoft/agent-framework/pull/2274))
- **observability**: Handle datetime serialization in tool results ([#2248](https://github.com/microsoft/agent-framework/pull/2248))

## [1.0.0b251117] - 2025-11-17

### Fixed

- **agent-framework-ag-ui**: Fix ag-ui state handling issues ([#2289](https://github.com/microsoft/agent-framework/pull/2289))

## [1.0.0b251114] - 2025-11-14

### Added

- **samples**: Bing Custom Search sample using `HostedWebSearchTool` ([#2226](https://github.com/microsoft/agent-framework/pull/2226))
- **samples**: Fabric and Browser Automation samples ([#2207](https://github.com/microsoft/agent-framework/pull/2207))
- **samples**: Hosted agent samples ([#2205](https://github.com/microsoft/agent-framework/pull/2205))
- **samples**: Azure OpenAI Responses API Hosted MCP sample ([#2108](https://github.com/microsoft/agent-framework/pull/2108))
- **samples**: Bing Grounding and Custom Search samples ([#2200](https://github.com/microsoft/agent-framework/pull/2200))

### Changed

- **agent-framework-azure-ai**: Enhance Azure AI Search citations with complete URL information ([#2066](https://github.com/microsoft/agent-framework/pull/2066))
- **agent-framework-azurefunctions**: Update samples to latest stable Azure Functions Worker packages ([#2189](https://github.com/microsoft/agent-framework/pull/2189))
- **agent-framework-azure-ai**: Agent name now required for `AzureAIClient` ([#2198](https://github.com/microsoft/agent-framework/pull/2198))
- **build**: Use `uv build` for packaging ([#2161](https://github.com/microsoft/agent-framework/pull/2161))
- **tooling**: Pre-commit improvements ([#2222](https://github.com/microsoft/agent-framework/pull/2222))
- **dependencies**: Updated package versions ([#2208](https://github.com/microsoft/agent-framework/pull/2208))

### Fixed

- **agent-framework-core**: Prevent duplicate MCP tools and prompts ([#1876](https://github.com/microsoft/agent-framework/pull/1876)) ([#1890](https://github.com/microsoft/agent-framework/pull/1890))
- **agent-framework-devui**: Fix HIL regression ([#2167](https://github.com/microsoft/agent-framework/pull/2167))
- **agent-framework-chatkit**: ChatKit sample fixes ([#2174](https://github.com/microsoft/agent-framework/pull/2174))

## [1.0.0b251112.post1] - 2025-11-12

### Added

- **agent-framework-azurefunctions**: Merge Azure Functions feature branch (#1916)

### Fixed

- **agent-framework-ag-ui**: fix tool call id mismatch in ag-ui ([#2166](https://github.com/microsoft/agent-framework/pull/2166))

## [1.0.0b251112] - 2025-11-12

### Added

- **agent-framework-azure-ai**: Azure AI client based on new `azure-ai-projects` package ([#1910](https://github.com/microsoft/agent-framework/pull/1910))
- **agent-framework-anthropic**: Add convenience method on data content ([#2083](https://github.com/microsoft/agent-framework/pull/2083))

### Changed

- **agent-framework-core**: Update OpenAI samples to use agents ([#2012](https://github.com/microsoft/agent-framework/pull/2012))

### Fixed

- **agent-framework-anthropic**: Fixed image handling in Anthropic client ([#2083](https://github.com/microsoft/agent-framework/pull/2083))

## [1.0.0b251111] - 2025-11-11

### Added

- **agent-framework-core**: Add OpenAI Responses Image Generation Stream Support with partial images and unit tests ([#1853](https://github.com/microsoft/agent-framework/pull/1853))
- **agent-framework-ag-ui**: Add concrete AGUIChatClient implementation ([#2072](https://github.com/microsoft/agent-framework/pull/2072))

### Fixed

- **agent-framework-a2a**: Use the last entry in the task history to avoid empty responses ([#2101](https://github.com/microsoft/agent-framework/pull/2101))
- **agent-framework-core**: Fix MCP Tool Parameter Descriptions not propagated to LLMs ([#1978](https://github.com/microsoft/agent-framework/pull/1978))
- **agent-framework-core**: Handle agent user input request in AgentExecutor ([#2022](https://github.com/microsoft/agent-framework/pull/2022))
- **agent-framework-core**: Fix Model ID attribute not showing up in `invoke_agent` span ([#2061](https://github.com/microsoft/agent-framework/pull/2061))
- **agent-framework-core**: Fix underlying tool choice bug and enable return to previous Handoff subagent ([#2037](https://github.com/microsoft/agent-framework/pull/2037))

## [1.0.0b251108] - 2025-11-08

### Added

- **agent-framework-devui**: Add OpenAI Responses API proxy support + HIL (Human-in-the-Loop) for Workflows ([#1737](https://github.com/microsoft/agent-framework/pull/1737))
- **agent-framework-purview**: Add Caching and background processing in Python Purview Middleware ([#1844](https://github.com/microsoft/agent-framework/pull/1844))

### Changed

- **agent-framework-devui**: Use metadata.entity_id instead of model field ([#1984](https://github.com/microsoft/agent-framework/pull/1984))
- **agent-framework-devui**: Serialize workflow input as string to maintain conformance with OpenAI Responses format ([#2021](https://github.com/microsoft/agent-framework/pull/2021))

## [1.0.0b251106.post1] - 2025-11-06

### Fixed

- **agent-framework-ag-ui**: Fix ag-ui examples packaging for PyPI publish ([#1953](https://github.com/microsoft/agent-framework/pull/1953))

## [1.0.0b251106] - 2025-11-06

### Changed

- **agent-framework-ag-ui**: export sample ag-ui agents ([#1927](https://github.com/microsoft/agent-framework/pull/1927))

## [1.0.0b251105] - 2025-11-05

### Added

- **agent-framework-ag-ui**: Initial release of AG-UI protocol integration for Agent Framework ([#1826](https://github.com/microsoft/agent-framework/pull/1826))
- **agent-framework-chatkit**: ChatKit integration with a sample application ([#1273](https://github.com/microsoft/agent-framework/pull/1273))
- Added parameter to disable agent cleanup in AzureAIAgentClient ([#1882](https://github.com/microsoft/agent-framework/pull/1882))
- Add support for Python 3.14 ([#1904](https://github.com/microsoft/agent-framework/pull/1904))

### Changed

- [BREAKING] Replaced AIProjectClient with AgentsClient in Foundry ([#1936](https://github.com/microsoft/agent-framework/pull/1936))
- Updates to Tools ([#1835](https://github.com/microsoft/agent-framework/pull/1835))

### Fixed

- Fix missing packaging dependency ([#1929](https://github.com/microsoft/agent-framework/pull/1929))

## [1.0.0b251104] - 2025-11-04

### Added

- Introducing the Anthropic Client ([#1819](https://github.com/microsoft/agent-framework/pull/1819))

### Changed

- [BREAKING] Consolidate workflow run APIs ([#1723](https://github.com/microsoft/agent-framework/pull/1723))
- [BREAKING] Remove request_type param from ctx.request_info() ([#1824](https://github.com/microsoft/agent-framework/pull/1824))
- [BREAKING] Cleanup of dependencies ([#1803](https://github.com/microsoft/agent-framework/pull/1803))
- [BREAKING] Replace `RequestInfoExecutor` with `request_info` API and `@response_handler` ([#1466](https://github.com/microsoft/agent-framework/pull/1466))
- Azure AI Search Support Update + Refactored Samples & Unit Tests ([#1683](https://github.com/microsoft/agent-framework/pull/1683))
- Lab: Updates to GAIA module ([#1763](https://github.com/microsoft/agent-framework/pull/1763))

### Fixed

- Azure AI `top_p` and `temperature` parameters fix ([#1839](https://github.com/microsoft/agent-framework/pull/1839))
- Ensure agent thread is part of checkpoint ([#1756](https://github.com/microsoft/agent-framework/pull/1756))
- Fix middleware and cleanup confusing function ([#1865](https://github.com/microsoft/agent-framework/pull/1865))
- Fix type compatibility check ([#1753](https://github.com/microsoft/agent-framework/pull/1753))
- Fix mcp tool cloning for handoff pattern ([#1883](https://github.com/microsoft/agent-framework/pull/1883))

## [1.0.0b251028] - 2025-10-28

### Added

- Added thread to AgentRunContext ([#1732](https://github.com/microsoft/agent-framework/pull/1732))
- AutoGen migration samples ([#1738](https://github.com/microsoft/agent-framework/pull/1738))
- Add Handoff orchestration pattern support ([#1469](https://github.com/microsoft/agent-framework/pull/1469))
- Added Samples for HostedCodeInterpreterTool with files ([#1583](https://github.com/microsoft/agent-framework/pull/1583))

### Changed

- [BREAKING] Introduce group chat and refactor orchestrations. Fix as_agent(). Standardize orchestration start msg types. ([#1538](https://github.com/microsoft/agent-framework/pull/1538))
- [BREAKING] Update Agent Framework Lab Lightning to use Agent-lightning v0.2.0 API ([#1644](https://github.com/microsoft/agent-framework/pull/1644))
- [BREAKING] Refactor Checkpointing for runner and runner context ([#1645](https://github.com/microsoft/agent-framework/pull/1645))
- Update lab packages and installation instructions ([#1687](https://github.com/microsoft/agent-framework/pull/1687))
- Remove deprecated add_agent() calls from workflow samples ([#1508](https://github.com/microsoft/agent-framework/pull/1508))

### Fixed

- Reject @executor on staticmethod/classmethod with clear error message ([#1719](https://github.com/microsoft/agent-framework/pull/1719))
- DevUI Fix Serialization, Timestamp and Other Issues ([#1584](https://github.com/microsoft/agent-framework/pull/1584))
- MCP Error Handling Fix + Added Unit Tests ([#1621](https://github.com/microsoft/agent-framework/pull/1621))
- InMemoryCheckpointManager is not JSON serializable ([#1639](https://github.com/microsoft/agent-framework/pull/1639))
- Fix gen_ai.operation.name to be invoke_agent ([#1729](https://github.com/microsoft/agent-framework/pull/1729))

## [1.0.0b251016] - 2025-10-16

### Added

- Add Purview Middleware ([#1142](https://github.com/microsoft/agent-framework/pull/1142))
- Added URL Citation Support to Azure AI Agent ([#1397](https://github.com/microsoft/agent-framework/pull/1397))
- Added MCP headers for AzureAI ([#1506](https://github.com/microsoft/agent-framework/pull/1506))
- Add Function Approval UI to DevUI ([#1401](https://github.com/microsoft/agent-framework/pull/1401))
- Added function approval example with streaming ([#1365](https://github.com/microsoft/agent-framework/pull/1365))
- Added A2A AuthInterceptor Support ([#1317](https://github.com/microsoft/agent-framework/pull/1317))
- Added example with MCP and authentication ([#1389](https://github.com/microsoft/agent-framework/pull/1389))
- Added sample with Foundry Redteams ([#1306](https://github.com/microsoft/agent-framework/pull/1306))
- Added AzureAI Agent AI Search Sample ([#1281](https://github.com/microsoft/agent-framework/pull/1281))
- Added AzureAI Bing Connection Name Support ([#1364](https://github.com/microsoft/agent-framework/pull/1364))

### Changed

- Enhanced documentation for dependency injection and serialization features ([#1324](https://github.com/microsoft/agent-framework/pull/1324))
- Update README to list all available examples ([#1394](https://github.com/microsoft/agent-framework/pull/1394))
- Reorganize workflows modules ([#1282](https://github.com/microsoft/agent-framework/pull/1282))
- Improved thread serialization and deserialization with better tests ([#1316](https://github.com/microsoft/agent-framework/pull/1316))
- Included existing agent definition in requests to Azure AI ([#1285](https://github.com/microsoft/agent-framework/pull/1285))
- DevUI - Internal Refactor, Conversations API support, and performance improvements ([#1235](https://github.com/microsoft/agent-framework/pull/1235))
- Refactor `RequestInfoExecutor` ([#1403](https://github.com/microsoft/agent-framework/pull/1403))

### Fixed

- Fix AI Search Tool Sample and improve AI Search Exceptions ([#1206](https://github.com/microsoft/agent-framework/pull/1206))
- Fix Failure with Function Approval Messages in Chat Clients ([#1322](https://github.com/microsoft/agent-framework/pull/1322))
- Fix deadlock in Magentic workflow ([#1325](https://github.com/microsoft/agent-framework/pull/1325))
- Fix tool call content not showing up in workflow events ([#1290](https://github.com/microsoft/agent-framework/pull/1290))
- Fixed instructions duplication in model clients ([#1332](https://github.com/microsoft/agent-framework/pull/1332))
- Agent Name Sanitization ([#1523](https://github.com/microsoft/agent-framework/pull/1523))

## [1.0.0b251007] - 2025-10-07

### Added

- Added method to expose agent as MCP server ([#1248](https://github.com/microsoft/agent-framework/pull/1248))
- Add PDF file support to OpenAI content parser with filename mapping ([#1121](https://github.com/microsoft/agent-framework/pull/1121))
- Sample on integration of Azure OpenAI Responses Client with a local MCP server ([#1215](https://github.com/microsoft/agent-framework/pull/1215))
- Added approval_mode and allowed_tools to local MCP ([#1203](https://github.com/microsoft/agent-framework/pull/1203))
- Introducing AI Function approval ([#1131](https://github.com/microsoft/agent-framework/pull/1131))
- Add name and description to workflows ([#1183](https://github.com/microsoft/agent-framework/pull/1183))
- Add Ollama example using OpenAIChatClient ([#1100](https://github.com/microsoft/agent-framework/pull/1100))
- Add DevUI improvements with color scheme, linking, agent details, and token usage data ([#1091](https://github.com/microsoft/agent-framework/pull/1091))
- Add semantic-kernel to agent-framework migration code samples ([#1045](https://github.com/microsoft/agent-framework/pull/1045))

### Changed

- [BREAKING] Parameter naming and other fixes ([#1255](https://github.com/microsoft/agent-framework/pull/1255))
- [BREAKING] Introduce add_agent functionality and added output_response to AgentExecutor; agent streaming behavior to follow workflow invocation ([#1184](https://github.com/microsoft/agent-framework/pull/1184))
- OpenAI Clients accepting api_key callback ([#1139](https://github.com/microsoft/agent-framework/pull/1139))
- Updated docstrings ([#1225](https://github.com/microsoft/agent-framework/pull/1225))
- Standardize docstrings: Use Keyword Args for Settings classes and add environment variable examples ([#1202](https://github.com/microsoft/agent-framework/pull/1202))
- Update References to Agent2Agent protocol to use correct terminology ([#1162](https://github.com/microsoft/agent-framework/pull/1162))
- Update getting started samples to reflect AF and update unit test ([#1093](https://github.com/microsoft/agent-framework/pull/1093))
- Update Lab Installation instructions to install from source ([#1051](https://github.com/microsoft/agent-framework/pull/1051))
- Update python DEV_SETUP to add brew-based uv installation ([#1173](https://github.com/microsoft/agent-framework/pull/1173))
- Update docstrings of all files and add example code in public interfaces ([#1107](https://github.com/microsoft/agent-framework/pull/1107))
- Clarifications on installing packages in README ([#1036](https://github.com/microsoft/agent-framework/pull/1036))
- DevUI Fixes ([#1035](https://github.com/microsoft/agent-framework/pull/1035))
- Packaging fixes: removed lab from dependencies, setup build/publish tasks, set homepage url ([#1056](https://github.com/microsoft/agent-framework/pull/1056))
- Agents + Chat Client Samples Docstring Updates ([#1028](https://github.com/microsoft/agent-framework/pull/1028))
- Python: Foundry Agent Completeness ([#954](https://github.com/microsoft/agent-framework/pull/954))

### Fixed

- Ollama + azureai openapi samples fix ([#1244](https://github.com/microsoft/agent-framework/pull/1244))
- Fix multimodal input sample: Document required environment variables and configuration options ([#1088](https://github.com/microsoft/agent-framework/pull/1088))
- Fix Azure AI Getting Started samples: Improve documentation and code readability ([#1089](https://github.com/microsoft/agent-framework/pull/1089))
- Fix a2a import ([#1058](https://github.com/microsoft/agent-framework/pull/1058))
- Fix DevUI serialization and agent structured outputs ([#1055](https://github.com/microsoft/agent-framework/pull/1055))
- Default DevUI workflows to string input when start node is auto-wrapped agent ([#1143](https://github.com/microsoft/agent-framework/pull/1143))
- Add missing pre flags on pip packages ([#1130](https://github.com/microsoft/agent-framework/pull/1130))


## [1.0.0b251001] - 2025-10-01

### Added

- First release of Agent Framework for Python
- agent-framework-core: Main abstractions, types and implementations for OpenAI and Azure OpenAI
- agent-framework-azure-ai: Integration with Azure AI Foundry Agents
- agent-framework-copilotstudio: Integration with Microsoft Copilot Studio agents
- agent-framework-a2a: Create A2A agents
- agent-framework-devui: Browser-based UI to chat with agents and workflows, with tracing visualization
- agent-framework-mem0 and agent-framework-redis: Integrations for Mem0 Context Provider and Redis Context Provider/Chat Memory Store
- agent-framework: Meta-package for installing all packages

For more information, see the [announcement blog post](https://devblogs.microsoft.com/foundry/introducing-microsoft-agent-framework-the-open-source-engine-for-agentic-ai-apps/).

[Unreleased]: https://github.com/microsoft/agent-framework/compare/python-1.0.0b260130...HEAD
[1.0.0b260130]: https://github.com/microsoft/agent-framework/compare/python-1.0.0b260128...python-1.0.0b260130
[1.0.0b260128]: https://github.com/microsoft/agent-framework/compare/python-1.0.0b260127...python-1.0.0b260128
[1.0.0b260127]: https://github.com/microsoft/agent-framework/compare/python-1.0.0b260123...python-1.0.0b260127
[1.0.0b260123]: https://github.com/microsoft/agent-framework/compare/python-1.0.0b260116...python-1.0.0b260123
[1.0.0b260116]: https://github.com/microsoft/agent-framework/compare/python-1.0.0b260114...python-1.0.0b260116
[1.0.0b260114]: https://github.com/microsoft/agent-framework/compare/python-1.0.0b260107...python-1.0.0b260114
[1.0.0b260107]: https://github.com/microsoft/agent-framework/compare/python-1.0.0b260106...python-1.0.0b260107
[1.0.0b260106]: https://github.com/microsoft/agent-framework/compare/python-1.0.0b251223...python-1.0.0b260106
[1.0.0b251223]: https://github.com/microsoft/agent-framework/compare/python-1.0.0b251218...python-1.0.0b251223
[1.0.0b251218]: https://github.com/microsoft/agent-framework/compare/python-1.0.0b251216...python-1.0.0b251218
[1.0.0b251216]: https://github.com/microsoft/agent-framework/compare/python-1.0.0b251211...python-1.0.0b251216
[1.0.0b251211]: https://github.com/microsoft/agent-framework/compare/python-1.0.0b251209...python-1.0.0b251211
[1.0.0b251209]: https://github.com/microsoft/agent-framework/compare/python-1.0.0b251204...python-1.0.0b251209
[1.0.0b251204]: https://github.com/microsoft/agent-framework/compare/python-1.0.0b251120...python-1.0.0b251204
[1.0.0b251120]: https://github.com/microsoft/agent-framework/compare/python-1.0.0b251117...python-1.0.0b251120
[1.0.0b251117]: https://github.com/microsoft/agent-framework/compare/python-1.0.0b251114...python-1.0.0b251117
[1.0.0b251114]: https://github.com/microsoft/agent-framework/compare/python-1.0.0b251112.post1...python-1.0.0b251114
[1.0.0b251112.post1]: https://github.com/microsoft/agent-framework/compare/python-1.0.0b251112...python-1.0.0b251112.post1
[1.0.0b251112]: https://github.com/microsoft/agent-framework/compare/python-1.0.0b251111...python-1.0.0b251112
[1.0.0b251111]: https://github.com/microsoft/agent-framework/compare/python-1.0.0b251108...python-1.0.0b251111
[1.0.0b251108]: https://github.com/microsoft/agent-framework/compare/python-1.0.0b251106.post1...python-1.0.0b251108
[1.0.0b251106.post1]: https://github.com/microsoft/agent-framework/compare/python-1.0.0b251106...python-1.0.0b251106.post1
[1.0.0b251106]: https://github.com/microsoft/agent-framework/compare/python-1.0.0b251105...python-1.0.0b251106
[1.0.0b251105]: https://github.com/microsoft/agent-framework/compare/python-1.0.0b251104...python-1.0.0b251105
[1.0.0b251104]: https://github.com/microsoft/agent-framework/compare/python-1.0.0b251028...python-1.0.0b251104
[1.0.0b251028]: https://github.com/microsoft/agent-framework/compare/python-1.0.0b251016...python-1.0.0b251028
[1.0.0b251016]: https://github.com/microsoft/agent-framework/compare/python-1.0.0b251007...python-1.0.0b251016
[1.0.0b251007]: https://github.com/microsoft/agent-framework/compare/python-1.0.0b251001...python-1.0.0b251007
[1.0.0b251001]: https://github.com/microsoft/agent-framework/releases/tag/python-1.0.0b251001
