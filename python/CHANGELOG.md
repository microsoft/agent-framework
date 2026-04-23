# Changelog

All notable changes to the Agent Framework Python packages will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [1.1.1] - 2026-04-23

### Added
- **agent-framework-core**: Add `expected_output` ground-truth support to `evaluate_workflow` for similarity evaluators ([#5234](https://github.com/microsoft/agent-framework/pull/5234))
- **agent-framework-ag-ui**, **agent-framework-a2a**: Propagate `thread_id` and `forwarded_props` through AG-UI to A2A `context_id` ([#5383](https://github.com/microsoft/agent-framework/pull/5383))
- **samples**: Add second approval-required tool (`set_stop_loss`) to `concurrent_builder_tool_approval` sample ([#4875](https://github.com/microsoft/agent-framework/pull/4875))
- **agent-framework-core**: Add `SKIP_PARSING` sentinel for `FunctionTool.invoke` to bypass `Content`-wrapping and return raw function results ([#5424](https://github.com/microsoft/agent-framework/pull/5424))

### Changed
- **agent-framework-foundry-hosting**: Correct Development Status classifier from Beta (4) to Alpha (3) to match the package's lifecycle stage ([#5387](https://github.com/microsoft/agent-framework/pull/5387))
- **tests**: Add Python flaky test report workflow ([#5342](https://github.com/microsoft/agent-framework/pull/5342))
- **agent-framework-hyperlight**: Simplify host callback to pass raw Python results via `SKIP_PARSING`, switch `execute_code` input schema to a plain JSON-schema dict, and tighten public API surface ([#5424](https://github.com/microsoft/agent-framework/pull/5424))

### Fixed
- **agent-framework-openai**: Fix OpenAI Responses streaming to propagate `created_at` from the final `response.completed` event ([#5382](https://github.com/microsoft/agent-framework/pull/5382))
- **agent-framework-openai**: Fix `OpenAIEmbeddingClient` to use `AsyncOpenAI` for `/openai/v1` endpoints ([#5137](https://github.com/microsoft/agent-framework/pull/5137))
- **agent-framework-openai**: Exclude null `file_id` from `input_image` payload to prevent schema 400 errors ([#5125](https://github.com/microsoft/agent-framework/pull/5125))
- **agent-framework-foundry**: Reconcile Toolbox hosted-tool payloads with the Responses API ([#5414](https://github.com/microsoft/agent-framework/pull/5414))
- **agent-framework-ag-ui**: Pass client `thread_id` as `session_id` when constructing `AgentSession` ([#5384](https://github.com/microsoft/agent-framework/pull/5384))
- **agent-framework-hyperlight**: Thread-confine `WasmSandbox` interactions via per-entry `ThreadPoolExecutor` to eliminate the PyO3 `unsendable` panic when touched from asyncio worker threads
  ([#5424](https://github.com/microsoft/agent-framework/pull/5424))

## [1.1.0] - 2026-04-21

### Added
- **agent-framework-gemini**: Add `GeminiChatClient` ([#4847](https://github.com/microsoft/agent-framework/pull/4847))
- **agent-framework-core**: Add `context_providers` and `description` to `workflow.as_agent()` ([#4651](https://github.com/microsoft/agent-framework/pull/4651))
- **agent-framework-core**: Add experimental file history provider ([#5248](https://github.com/microsoft/agent-framework/pull/5248))
- **agent-framework-core**: Add OpenAI types to the default checkpoint encoding allow list ([#5297](https://github.com/microsoft/agent-framework/pull/5297))
- **agent-framework-core**: Add `AgentExecutorResponse.with_text()` to preserve conversation history through custom executors ([#5255](https://github.com/microsoft/agent-framework/pull/5255))
- **agent-framework-a2a**: Propagate A2A metadata from `Message`, `Artifact`, `Task`, and event types ([#5256](https://github.com/microsoft/agent-framework/pull/5256))
- **agent-framework-core**: Add `finish_reason` support to `AgentResponse` and `AgentResponseUpdate` ([#5211](https://github.com/microsoft/agent-framework/pull/5211))
- **agent-framework-hyperlight**: Add Hyperlight CodeAct package and docs ([#5185](https://github.com/microsoft/agent-framework/pull/5185))
- **agent-framework-openai**: Add search tool content support for OpenAI responses ([#5302](https://github.com/microsoft/agent-framework/pull/5302))
- **agent-framework-foundry**: Add support for Foundry Toolboxes ([#5346](https://github.com/microsoft/agent-framework/pull/5346))
- **agent-framework-ag-ui**: Expose `forwardedProps` to agents and tools via session metadata ([#5264](https://github.com/microsoft/agent-framework/pull/5264))
- **agent-framework-foundry**: Add hosted agent V2 support ([#5379](https://github.com/microsoft/agent-framework/pull/5379))

### Changed
- **agent-framework-azure-cosmos**: [BREAKING] `CosmosCheckpointStorage` now uses restricted pickle deserialization by default, matching `FileCheckpointStorage` behavior. If your checkpoints contain application-defined types, pass them via `allowed_checkpoint_types=["my_app.models:MyState"]`. ([#5200](https://github.com/microsoft/agent-framework/issues/5200))
- **agent-framework-core**: Improve skill name validation ([#4530](https://github.com/microsoft/agent-framework/pull/4530))
- **agent-framework-azure-cosmos**: Add `allowed_checkpoint_types` support to `CosmosCheckpointStorage` for parity with `FileCheckpointStorage` ([#5202](https://github.com/microsoft/agent-framework/pull/5202))
- **agent-framework-core**: Move `InMemory` history provider injection to first invocation ([#5236](https://github.com/microsoft/agent-framework/pull/5236))
- **agent-framework-github-copilot**: Forward provider config to `SessionConfig` in `GitHubCopilotAgent` ([#5195](https://github.com/microsoft/agent-framework/pull/5195))
- **agent-framework-hyperlight-codeact**: Flatten `execute_code` output ([#5333](https://github.com/microsoft/agent-framework/pull/5333))
- **dependencies**: Bump `pygments` from `2.19.2` to `2.20.0` in `/python` ([#4978](https://github.com/microsoft/agent-framework/pull/4978))
- **tests**: Bump misc integration retry delay to 30s ([#5293](https://github.com/microsoft/agent-framework/pull/5293))
- **tests**: Improve misc integration test robustness ([#5295](https://github.com/microsoft/agent-framework/pull/5295))
- **tests**: Skip hosted tools test on transient upstream MCP errors ([#5296](https://github.com/microsoft/agent-framework/pull/5296))

### Fixed
- **agent-framework-core**: Fix `python-feature-lifecycle` skill YAML frontmatter ([#5226](https://github.com/microsoft/agent-framework/pull/5226))
- **agent-framework-core**: Fix `HandoffBuilder` dropping function-level middleware when cloning agents ([#5220](https://github.com/microsoft/agent-framework/pull/5220))
- **agent-framework-ag-ui**: Fix deterministic state updates from tool results ([#5201](https://github.com/microsoft/agent-framework/pull/5201))
- **agent-framework-devui**: Fix streaming memory growth and add cross-platform regression coverage ([#5221](https://github.com/microsoft/agent-framework/pull/5221))
- **agent-framework-core**: Skip `get_final_response` in `_finalize_stream` when the stream has errored ([#5232](https://github.com/microsoft/agent-framework/pull/5232))
- **agent-framework-openai**: Fix reasoning replay when `store=False` ([#5250](https://github.com/microsoft/agent-framework/pull/5250))
- **agent-framework-foundry**: Handle `url_citation` annotations in `FoundryChatClient` streaming responses ([#5071](https://github.com/microsoft/agent-framework/pull/5071))
- **agent-framework-gemini**: Fix Gemini client support for Gemini API and Vertex AI ([#5258](https://github.com/microsoft/agent-framework/pull/5258))
- **agent-framework-copilotstudio**: Fix `CopilotStudioAgent` to reuse conversation ID from an existing session ([#5299](https://github.com/microsoft/agent-framework/pull/5299))

## [devui-1.0.0b260414] - 2026-04-14

### Fixed
- **agent-framework-devui**: Fix streaming memory growth in DevUI frontend ([#5221](https://github.com/microsoft/agent-framework/pull/5221))

## [1.0.1] - 2026-04-09

### Added
- **samples**: Add sample documentation for two separate Neo4j context providers for retrieval and memory ([#4010](https://github.com/microsoft/agent-framework/pull/4010))
- **agent-framework-azure-cosmos**: Add Cosmos DB NoSQL checkpoint storage for Python workflows ([#4916](https://github.com/microsoft/agent-framework/pull/4916))

### Changed
- **docs**: Remove pre-release flag from agent-framework installation instructions ([#5082](https://github.com/microsoft/agent-framework/pull/5082))
- **samples**: Revise agent examples in `README.md` ([#5067](https://github.com/microsoft/agent-framework/pull/5067))
- **repo**: Update `CHANGELOG` with v1.0.0 release ([#5069](https://github.com/microsoft/agent-framework/pull/5069))
- **agent-framework-orchestrations**: [BREAKING] Fix handoff workflow context management and improve AG-UI demo ([#5136](https://github.com/microsoft/agent-framework/pull/5136))
- **agent-framework-core**: Restrict persisted checkpoint deserialization by default ([#4941](https://github.com/microsoft/agent-framework/pull/4941))
- **samples**: Bump `vite` from 7.3.1 to 7.3.2 in `/python/samples/05-end-to-end/ag_ui_workflow_handoff/frontend` ([#5132](https://github.com/microsoft/agent-framework/pull/5132))
- **python**: Bump `cryptography` from 46.0.6 to 46.0.7 ([#5176](https://github.com/microsoft/agent-framework/pull/5176))
- **python**: Bump `mcp` from 1.26.0 to 1.27.0 ([#5117](https://github.com/microsoft/agent-framework/pull/5117))
- **python**: Bump `mcp[ws]` from 1.26.0 to 1.27.0 ([#5119](https://github.com/microsoft/agent-framework/pull/5119))

### Fixed
- **agent-framework-core**: Raise clear handler registration error for unresolved `TypeVar` annotations ([#4944](https://github.com/microsoft/agent-framework/pull/4944))
- **agent-framework-openai**: Fix `response_format` crash on background polling with empty text ([#5146](https://github.com/microsoft/agent-framework/pull/5146))
- **agent-framework-foundry**: Strip tools from `FoundryAgent` request when `agent_reference` is present ([#5101](https://github.com/microsoft/agent-framework/pull/5101))
- **agent-framework-core**: Fix test compatibility for entity key validation ([#5179](https://github.com/microsoft/agent-framework/pull/5179))
- **agent-framework-openai**: Stop emitting duplicate reasoning content from `response.reasoning_text.done` and `response.reasoning_summary_text.done` events ([#5162](https://github.com/microsoft/agent-framework/pull/5162))


## [1.0.0] - 2026-04-02

### Added

- **repo**: Add `PACKAGE_STATUS.md` to track lifecycle status of all Python packages ([#5062](https://github.com/microsoft/agent-framework/pull/5062))

### Changed

- **agent-framework**, **agent-framework-core**, **agent-framework-openai**, **agent-framework-foundry**: [BREAKING] Promote from `1.0.0rc6` to `1.0.0` (Production/Stable) ([#5062](https://github.com/microsoft/agent-framework/pull/5062))
- **agent-framework-core**, **agent-framework-openai**, **agent-framework-foundry**: [BREAKING] Dependency floors now require released `>=1.0.0,<2` packages, breaking compatibility with older RC installs ([#5062](https://github.com/microsoft/agent-framework/pull/5062))
- **agent-framework-a2a**, **agent-framework-ag-ui**, **agent-framework-anthropic**, **agent-framework-azure-ai-search**, **agent-framework-azure-cosmos**, **agent-framework-azurefunctions**, **agent-framework-bedrock**, **agent-framework-chatkit**, **agent-framework-claude**, **agent-framework-copilotstudio**, **agent-framework-declarative**, **agent-framework-devui**, **agent-framework-durabletask**, **agent-framework-foundry-local**, **agent-framework-github-copilot**, **agent-framework-lab**, **agent-framework-mem0**, **agent-framework-ollama**, **agent-framework-orchestrations**, **agent-framework-purview**, **agent-framework-redis**: Bump beta versions from `1.0.0b260330` to `1.0.0b260402` ([#5062](https://github.com/microsoft/agent-framework/pull/5062))
- **docs**: Update install instructions to drop `--pre` flag for released packages ([#5062](https://github.com/microsoft/agent-framework/pull/5062))

### Removed

- **agent-framework-core**: [BREAKING] Remove deprecated `BaseContextProvider` and `BaseHistoryProvider` aliases ([#5062](https://github.com/microsoft/agent-framework/pull/5062))
- **agent-framework-core**: [BREAKING] Remove deprecated `text` parameter from `Message` constructor ([#5062](https://github.com/microsoft/agent-framework/pull/5062))

### Fixed

- **agent-framework-core**, **agent-framework-openai**, **agent-framework-foundry**, **agent-framework-azurefunctions**, **agent-framework-devui**, **agent-framework-orchestrations**, **agent-framework-azure-ai-search**: Migrate message construction from `Message(text=...)` to `Message(contents=[...])` throughout codebase ([#5062](https://github.com/microsoft/agent-framework/pull/5062))
- **agent-framework-devui**: Accept legacy payload formats (`text`, `message`, `content`, `input`, `data`) and convert to framework-native `Message(contents=...)` ([#5062](https://github.com/microsoft/agent-framework/pull/5062))
- **samples**: Fix Foundry samples to use env vars consistently and update install guidance ([#5062](https://github.com/microsoft/agent-framework/pull/5062))

## [1.0.0rc6] - 2026-03-30

### Added

- **agent-framework-openai**: New package extracted from core for OpenAI and Azure OpenAI provider support ([#4818](https://github.com/microsoft/agent-framework/pull/4818))
- **agent-framework-foundry**: New package for Azure AI Foundry integration ([#4818](https://github.com/microsoft/agent-framework/pull/4818))
- **agent-framework-core**: Support `structuredContent` in MCP tool results and fix sampling options type ([#4763](https://github.com/microsoft/agent-framework/pull/4763))
- **agent-framework-core**: Include reasoning messages in `MESSAGES_SNAPSHOT` events ([#4844](https://github.com/microsoft/agent-framework/pull/4844))
- **agent-framework-core**: [BREAKING] Add context mode to `AgentExecutor` ([#4668](https://github.com/microsoft/agent-framework/pull/4668))

### Changed

- **agent-framework-core**: [BREAKING] Remove deprecated kwargs compatibility paths ([#4858](https://github.com/microsoft/agent-framework/pull/4858))
- **agent-framework-core**: [BREAKING] Reduce core dependencies and simplify optional integrations ([#4904](https://github.com/microsoft/agent-framework/pull/4904))
- **agent-framework-openai**: [BREAKING] Provider-leading client design & OpenAI package extraction ([#4818](https://github.com/microsoft/agent-framework/pull/4818))
- **agent-framework-openai**: [BREAKING] Fix OpenAI Azure routing and provider samples ([#4925](https://github.com/microsoft/agent-framework/pull/4925))
- **agent-framework-azure-ai**: Deprecate Azure AI v1 (Persistent Agents API) helper methods ([#4804](https://github.com/microsoft/agent-framework/pull/4804))
- **agent-framework-core**: Avoid duplicate agent response telemetry ([#4685](https://github.com/microsoft/agent-framework/pull/4685))
- **agent-framework-devui**: Bump `flatted` from 3.3.3 to 3.4.2 in frontend ([#4805](https://github.com/microsoft/agent-framework/pull/4805))
- **samples**: Move `ag_ui_workflow_handoff` demo from `demos/` to `05-end-to-end/` ([#4900](https://github.com/microsoft/agent-framework/pull/4900))

### Fixed

- **agent-framework-core**: Fix streaming path to emit `mcp_server_tool_result` on `output_item.done` instead of `output_item.added` ([#4821](https://github.com/microsoft/agent-framework/pull/4821))
- **agent-framework-a2a**: Fix `A2AAgent` to surface message content from in-progress `TaskStatusUpdateEvents` ([#4798](https://github.com/microsoft/agent-framework/pull/4798))
- **agent-framework-core**: Fix `PydanticSchemaGenerationError` when using `from __future__ import annotations` with `@tool` ([#4822](https://github.com/microsoft/agent-framework/pull/4822))
- **samples**: Fix broken samples for GitHub Copilot, declarative, and Responses API ([#4915](https://github.com/microsoft/agent-framework/pull/4915))
- **repo**: Fix: update PyRIT repository link from Azure/PyRIT to microsoft/PyRIT ([#4960](https://github.com/microsoft/agent-framework/pull/4960))

## [1.0.0rc5] - 2026-03-19

### Added

- **samples**: Add foundry hosted agents samples for python ([#4648](https://github.com/microsoft/agent-framework/pull/4648))
- **repo**: Add automated stale issue and PR follow-up ping workflow ([#4776](https://github.com/microsoft/agent-framework/pull/4776))
- **agent-framework-ag-ui**: Emit AG-UI events for MCP tool calls, results, and text reasoning ([#4760](https://github.com/microsoft/agent-framework/pull/4760))
- **agent-framework-ag-ui**: Emit TOOL_CALL_RESULT events when resuming after tool approval ([#4758](https://github.com/microsoft/agent-framework/pull/4758))

### Changed

- **agent-framework-devui**: Bump minimatch from 3.1.2 to 3.1.5 in frontend ([#4337](https://github.com/microsoft/agent-framework/pull/4337))
- **agent-framework-devui**: Bump rollup from 4.47.1 to 4.59.0 in frontend ([#4338](https://github.com/microsoft/agent-framework/pull/4338))
- **agent-framework-core**: Unify tool results as `Content` items with rich content support ([#4331](https://github.com/microsoft/agent-framework/pull/4331))
- **agent-framework-a2a**: Default `A2AAgent` name and description from `AgentCard` ([#4661](https://github.com/microsoft/agent-framework/pull/4661))
- **agent-framework-core**: [BREAKING] Clean up kwargs across agents, chat clients, tools, and sessions ([#4581](https://github.com/microsoft/agent-framework/pull/4581))
- **agent-framework-devui**: Bump tar from 7.5.9 to 7.5.11 ([#4688](https://github.com/microsoft/agent-framework/pull/4688))
- **repo**: Improve Python dependency range automation ([#4343](https://github.com/microsoft/agent-framework/pull/4343))
- **agent-framework-core**: Normalize empty MCP tool output to `null` ([#4683](https://github.com/microsoft/agent-framework/pull/4683))
- **agent-framework-core**: Remove bad dependency ([#4696](https://github.com/microsoft/agent-framework/pull/4696))
- **agent-framework-core**: Keep MCP cleanup on the owner task ([#4687](https://github.com/microsoft/agent-framework/pull/4687))
- **agent-framework-a2a**: Preserve A2A message `context_id` ([#4686](https://github.com/microsoft/agent-framework/pull/4686))
- **repo**: Bump `danielpalme/ReportGenerator-GitHub-Action` from 5.5.1 to 5.5.3 ([#4542](https://github.com/microsoft/agent-framework/pull/4542))
- **repo**: Bump `MishaKav/pytest-coverage-comment` from 1.2.0 to 1.6.0 ([#4543](https://github.com/microsoft/agent-framework/pull/4543))
- **agent-framework-core**: Bump `pyjwt` from 2.11.0 to 2.12.0 ([#4699](https://github.com/microsoft/agent-framework/pull/4699))
- **agent-framework-azure-ai**: Reduce Azure chat client import overhead ([#4744](https://github.com/microsoft/agent-framework/pull/4744))
- **repo**: Simplify Python Poe tasks and unify package selectors ([#4722](https://github.com/microsoft/agent-framework/pull/4722))
- **agent-framework-core**: Aggregate token usage across tool-call loop iterations in `invoke_agent` span ([#4739](https://github.com/microsoft/agent-framework/pull/4739))
- **agent-framework-core**: Support `detail` field in OpenAI Chat API `image_url` payload ([#4756](https://github.com/microsoft/agent-framework/pull/4756))
- **agent-framework-anthropic**: [BREAKING] Refactor middleware layering and split Anthropic raw client ([#4746](https://github.com/microsoft/agent-framework/pull/4746))
- **agent-framework-github-copilot**: Emit tool call events in GitHubCopilotAgent streaming ([4711](https://github.com/microsoft/agent-framework/pull/4711))

### Fixed

- **agent-framework-core**: Validate approval responses against the server-side pending request registry ([#4548](https://github.com/microsoft/agent-framework/pull/4548))
- **agent-framework-devui**: Validate function approval responses in the DevUI executor ([#4598](https://github.com/microsoft/agent-framework/pull/4598))
- **agent-framework-azurefunctions**: Use `deepcopy` for state snapshots so nested mutations are detected in durable workflow activities ([#4518](https://github.com/microsoft/agent-framework/pull/4518))
- **agent-framework-bedrock**: Fix `BedrockChatClient` sending invalid toolChoice `"none"` to the Bedrock API ([#4535](https://github.com/microsoft/agent-framework/pull/4535))
- **agent-framework-core**: Fix type hint for `Case` and `Default` ([#3985](https://github.com/microsoft/agent-framework/pull/3985))
- **agent-framework-core**: Fix duplicate tool names between supplied tools and MCP servers ([#4649](https://github.com/microsoft/agent-framework/pull/4649))
- **agent-framework-core**: Fix `_deduplicate_messages` catch-all branch dropping valid repeated messages ([#4716](https://github.com/microsoft/agent-framework/pull/4716))
- **samples**: Fix Azure Redis sample missing session for history persistence ([#4692](https://github.com/microsoft/agent-framework/pull/4692))
- **agent-framework-core**: Fix thread serialization for multi-turn tool calls ([#4684](https://github.com/microsoft/agent-framework/pull/4684))
- **agent-framework-core**: Fix `RUN_FINISHED.interrupt` to accumulate all interrupts when multiple tools need approval ([#4717](https://github.com/microsoft/agent-framework/pull/4717))
- **agent-framework-azurefunctions**: Fix missing methods on the `Content` class in durable tasks ([#4738](https://github.com/microsoft/agent-framework/pull/4738))
- **agent-framework-core**: Fix `ENABLE_SENSITIVE_DATA` being ignored when set after module import ([#4743](https://github.com/microsoft/agent-framework/pull/4743))
- **agent-framework-a2a**: Fix `A2AAgent` to invoke context providers before and after run ([#4757](https://github.com/microsoft/agent-framework/pull/4757))
- **agent-framework-core**: Fix MCP tool schema normalization for zero-argument tools missing the `properties` key ([#4771](https://github.com/microsoft/agent-framework/pull/4771))

## [1.0.0rc4] - 2026-03-11

### Added

- **agent-framework-core**: Add `propagate_session` to `as_tool()` for session sharing in agent-as-tool scenarios ([#4439](https://github.com/microsoft/agent-framework/pull/4439))
- **agent-framework-core**: Forward runtime kwargs to skill resource functions ([#4417](https://github.com/microsoft/agent-framework/pull/4417))
- **samples**: Add A2A server sample ([#4528](https://github.com/microsoft/agent-framework/pull/4528))

### Changed

- **agent-framework-github-copilot**: [BREAKING] Update integration to use `ToolInvocation` and `ToolResult` types ([#4551](https://github.com/microsoft/agent-framework/pull/4551))
- **agent-framework-azure-ai**: [BREAKING] Upgrade to `azure-ai-projects` 2.0+ ([#4536](https://github.com/microsoft/agent-framework/pull/4536))

### Fixed

- **agent-framework-core**: Propagate MCP `isError` flag through the function middleware pipeline ([#4511](https://github.com/microsoft/agent-framework/pull/4511))
- **agent-framework-core**: Fix `as_agent()` not defaulting name/description from client properties ([#4484](https://github.com/microsoft/agent-framework/pull/4484))
- **agent-framework-core**: Exclude `conversation_id` from chat completions API options ([#4517](https://github.com/microsoft/agent-framework/pull/4517))
- **agent-framework-core**: Fix conversation ID propagation when `chat_options` is a dict ([#4340](https://github.com/microsoft/agent-framework/pull/4340))
- **agent-framework-core**: Auto-finalize `ResponseStream` on iteration completion ([#4478](https://github.com/microsoft/agent-framework/pull/4478))
- **agent-framework-core**: Prevent pickle deserialization of untrusted HITL HTTP input ([#4566](https://github.com/microsoft/agent-framework/pull/4566))
- **agent-framework-core**: Fix `executor_completed` event handling for non-copyable `raw_representation` in mixed workflows ([#4493](https://github.com/microsoft/agent-framework/pull/4493))
- **agent-framework-core**: Fix `store=False` not overriding client default ([#4569](https://github.com/microsoft/agent-framework/pull/4569))
- **agent-framework-redis**: Fix `RedisContextProvider` compatibility with redisvl 0.14.0 by using `AggregateHybridQuery` ([#3954](https://github.com/microsoft/agent-framework/pull/3954))
- **samples**: Fix `chat_response_cancellation` sample to use `Message` objects ([#4532](https://github.com/microsoft/agent-framework/pull/4532))
- **agent-framework-purview**: Fix broken link in Purview README (Microsoft 365 Dev Program URL) ([#4610](https://github.com/microsoft/agent-framework/pull/4610))

## [1.0.0rc3] - 2026-03-04

### Added

- **agent-framework-core**: Add Shell tool ([#4339](https://github.com/microsoft/agent-framework/pull/4339))
- **agent-framework-core**: Add `file_ids` and `data_sources` support to `get_code_interpreter_tool()` ([#4201](https://github.com/microsoft/agent-framework/pull/4201))
- **agent-framework-core**: Map file citation annotations from `TextDeltaBlock` in Assistants API streaming ([#4316](https://github.com/microsoft/agent-framework/pull/4316), [#4320](https://github.com/microsoft/agent-framework/pull/4320))
- **agent-framework-claude**: Add OpenTelemetry instrumentation to `ClaudeAgent` ([#4278](https://github.com/microsoft/agent-framework/pull/4278), [#4326](https://github.com/microsoft/agent-framework/pull/4326))
- **agent-framework-azure-cosmos**: Add Azure Cosmos history provider package ([#4271](https://github.com/microsoft/agent-framework/pull/4271))
- **samples**: Add `auto_retry.py` sample for rate limit handling ([#4223](https://github.com/microsoft/agent-framework/pull/4223))
- **tests**: Add regression tests for Entry JoinExecutor workflow input initialization ([#4335](https://github.com/microsoft/agent-framework/pull/4335))

### Changed

- **samples**: Restructure and improve Python samples ([#4092](https://github.com/microsoft/agent-framework/pull/4092))
- **agent-framework-orchestrations**: [BREAKING] Tighten `HandoffBuilder` to require `Agent` instead of `SupportsAgentRun` ([#4301](https://github.com/microsoft/agent-framework/pull/4301), [#4302](https://github.com/microsoft/agent-framework/pull/4302))
- **samples**: Update workflow orchestration samples to use `AzureOpenAIResponsesClient` ([#4285](https://github.com/microsoft/agent-framework/pull/4285))

### Fixed

- **agent-framework-bedrock**: Fix embedding test stub missing `meta` attribute ([#4287](https://github.com/microsoft/agent-framework/pull/4287))
- **agent-framework-ag-ui**: Fix approval payloads being re-processed on subsequent conversation turns ([#4232](https://github.com/microsoft/agent-framework/pull/4232))
- **agent-framework-core**: Fix `response_format` resolution in streaming finalizer ([#4291](https://github.com/microsoft/agent-framework/pull/4291))
- **agent-framework-core**: Strip reserved kwargs in `AgentExecutor` to prevent duplicate-argument `TypeError` ([#4298](https://github.com/microsoft/agent-framework/pull/4298))
- **agent-framework-core**: Preserve workflow run kwargs when continuing with `run(responses=...)` ([#4296](https://github.com/microsoft/agent-framework/pull/4296))
- **agent-framework-core**: Fix `WorkflowAgent` not persisting response messages to session history ([#4319](https://github.com/microsoft/agent-framework/pull/4319))
- **agent-framework-core**: Fix single-tool input handling in `OpenAIResponsesClient._prepare_tools_for_openai` ([#4312](https://github.com/microsoft/agent-framework/pull/4312))
- **agent-framework-core**: Fix agent option merge to support dict-defined tools ([#4314](https://github.com/microsoft/agent-framework/pull/4314))
- **agent-framework-core**: Fix executor handler type resolution when using `from __future__ import annotations` ([#4317](https://github.com/microsoft/agent-framework/pull/4317))
- **agent-framework-core**: Fix walrus operator precedence for `model_id` kwarg in `AzureOpenAIResponsesClient` ([#4310](https://github.com/microsoft/agent-framework/pull/4310))
- **agent-framework-core**: Handle `thread.message.completed` event in Assistants API streaming ([#4333](https://github.com/microsoft/agent-framework/pull/4333))
- **agent-framework-core**: Fix MCP tools duplicated on second turn when runtime tools are present ([#4432](https://github.com/microsoft/agent-framework/pull/4432))
- **agent-framework-core**: Fix PowerFx eval crash on non-English system locales by setting `CurrentUICulture` to `en-US` ([#4408](https://github.com/microsoft/agent-framework/pull/4408))
- **agent-framework-orchestrations**: Fix `StandardMagenticManager` to propagate session to manager agent ([#4409](https://github.com/microsoft/agent-framework/pull/4409))
- **agent-framework-orchestrations**: Fix `IndexError` when reasoning models produce reasoning-only messages in Magentic-One workflow ([#4413](https://github.com/microsoft/agent-framework/pull/4413))
- **agent-framework-azure-ai**: Fix parsing `oauth_consent_request` events in Azure AI client ([#4197](https://github.com/microsoft/agent-framework/pull/4197))
- **agent-framework-anthropic**: Set `role="assistant"` on `message_start` streaming update ([#4329](https://github.com/microsoft/agent-framework/pull/4329))
- **samples**: Fix samples discovered by auto validation pipeline ([#4355](https://github.com/microsoft/agent-framework/pull/4355))
- **samples**: Use `AgentResponse.value` instead of `model_validate_json` in HITL sample ([#4405](https://github.com/microsoft/agent-framework/pull/4405))
- **agent-framework-devui**: Fix .NET conversation memory handling in DevUI integration ([#3484](https://github.com/microsoft/agent-framework/pull/3484), [#4294](https://github.com/microsoft/agent-framework/pull/4294))

## [1.0.0rc2] - 2026-02-25

### Added

- **agent-framework-core**: Support Agent Skills ([#4210](https://github.com/microsoft/agent-framework/pull/4210))
- **agent-framework-core**: Add embedding abstractions and OpenAI implementation (Phase 1) ([#4153](https://github.com/microsoft/agent-framework/pull/4153))
- **agent-framework-core**: Add Foundry Memory Context Provider ([#3943](https://github.com/microsoft/agent-framework/pull/3943))
- **agent-framework-core**: Add `max_function_calls` to `FunctionInvocationConfiguration` ([#4175](https://github.com/microsoft/agent-framework/pull/4175))
- **agent-framework-core**: Add `CreateConversationExecutor`, fix input routing, remove unused handler layer ([#4159](https://github.com/microsoft/agent-framework/pull/4159))
- **agent-framework-azure-ai-search**: Azure AI Search provider improvements - EmbeddingGenerator, async context manager, KB message handling ([#4212](https://github.com/microsoft/agent-framework/pull/4212))
- **agent-framework-azure-ai-search**: Enhance Azure AI Search Citations with Document URLs in Foundry V2 ([#4028](https://github.com/microsoft/agent-framework/pull/4028))
- **agent-framework-ag-ui**: Add Workflow Support, Harden Streaming Semantics, and add Dynamic Handoff Demo ([#3911](https://github.com/microsoft/agent-framework/pull/3911))

### Changed

- **agent-framework-declarative**: [BREAKING] Add `InvokeFunctionTool` action for declarative workflows ([#3716](https://github.com/microsoft/agent-framework/pull/3716))

### Fixed

- **agent-framework-core**: Fix thread corruption when `max_iterations` is reached ([#4234](https://github.com/microsoft/agent-framework/pull/4234))
- **agent-framework-core**: Fix workflow runner concurrent processing ([#4143](https://github.com/microsoft/agent-framework/pull/4143))
- **agent-framework-core**: Fix doubled `tool_call` arguments in `MESSAGES_SNAPSHOT` when streaming ([#4200](https://github.com/microsoft/agent-framework/pull/4200))
- **agent-framework-core**: Fix OpenAI chat client compatibility with third-party endpoints and OTel 0.4.14 ([#4161](https://github.com/microsoft/agent-framework/pull/4161))
- **agent-framework-claude**: Fix `structured_output` propagation in `ClaudeAgent` ([#4137](https://github.com/microsoft/agent-framework/pull/4137))

## [1.0.0rc1] - 2026-02-19

Release candidate for **agent-framework-core** and **agent-framework-azure-ai** packages.

### Added

- **agent-framework-core**: Add default in-memory history provider for workflow agents ([#3918](https://github.com/microsoft/agent-framework/pull/3918))
- **agent-framework-core**: Durable support for workflows ([#3630](https://github.com/microsoft/agent-framework/pull/3630))

### Changed

- **agent-framework-core**: [BREAKING] Scope provider state by `source_id` and standardize source IDs ([#3995](https://github.com/microsoft/agent-framework/pull/3995))
- **agent-framework-core**: [BREAKING] Fix chat/agent message typing alignment ([#3920](https://github.com/microsoft/agent-framework/pull/3920))
- **agent-framework-core**: [BREAKING] Remove `FunctionTool[Any]` compatibility shim for schema passthrough ([#3907](https://github.com/microsoft/agent-framework/pull/3907))
- **agent-framework-core**: Inject OpenTelemetry trace context into MCP requests ([#3780](https://github.com/microsoft/agent-framework/pull/3780))
- **agent-framework-core**: Replace wildcard imports with explicit imports ([#3908](https://github.com/microsoft/agent-framework/pull/3908))

### Fixed

- **agent-framework-core**: Fix hosted MCP tool approval flow for all session/streaming combinations ([#4054](https://github.com/microsoft/agent-framework/pull/4054))
- **agent-framework-core**: Prevent repeating instructions in continued Responses API conversations ([#3909](https://github.com/microsoft/agent-framework/pull/3909))
- **agent-framework-core**: Add missing system instruction attribute to `invoke_agent` span ([#4012](https://github.com/microsoft/agent-framework/pull/4012))
- **agent-framework-core**: Fix tool normalization and provider sample consolidation ([#3953](https://github.com/microsoft/agent-framework/pull/3953))
- **agent-framework-azure-ai**: Warn on unsupported AzureAIClient runtime tool/structured_output overrides ([#3919](https://github.com/microsoft/agent-framework/pull/3919))
- **agent-framework-azure-ai-search**: Improve Azure AI Search package test coverage ([#4019](https://github.com/microsoft/agent-framework/pull/4019))
- **agent-framework-anthropic**: Fix Anthropic option conflicts and manager parse retries ([#4000](https://github.com/microsoft/agent-framework/pull/4000))
- **agent-framework-anthropic**: Track and enforce 85%+ unit test coverage for anthropic package ([#3926](https://github.com/microsoft/agent-framework/pull/3926))
- **agent-framework-azurefunctions**: Achieve 85%+ unit test coverage for azurefunctions package ([#3866](https://github.com/microsoft/agent-framework/pull/3866))
- **samples**: Fix workflow, declarative, Redis, Anthropic, GitHub Copilot, Azure AI, MCP, eval, and migration samples ([#4055](https://github.com/microsoft/agent-framework/pull/4055), [#4051](https://github.com/microsoft/agent-framework/pull/4051), [#4049](https://github.com/microsoft/agent-framework/pull/4049), [#4046](https://github.com/microsoft/agent-framework/pull/4046), [#4033](https://github.com/microsoft/agent-framework/pull/4033), [#4030](https://github.com/microsoft/agent-framework/pull/4030), [#4027](https://github.com/microsoft/agent-framework/pull/4027), [#4032](https://github.com/microsoft/agent-framework/pull/4032), [#4025](https://github.com/microsoft/agent-framework/pull/4025), [#4021](https://github.com/microsoft/agent-framework/pull/4021), [#4022](https://github.com/microsoft/agent-framework/pull/4022), [#4001](https://github.com/microsoft/agent-framework/pull/4001))

## [1.0.0b260212] - 2026-02-12

### Added

- **agent-framework-core**: Allow `AzureOpenAIResponsesClient` creation with Foundry project endpoint ([#3814](https://github.com/microsoft/agent-framework/pull/3814))

### Changed

- **agent-framework-core**: [BREAKING] Wire context provider pipeline, remove old types, update all consumers ([#3850](https://github.com/microsoft/agent-framework/pull/3850))
- **agent-framework-core**: [BREAKING] Checkpoint refactor: encode/decode, checkpoint format, etc ([#3744](https://github.com/microsoft/agent-framework/pull/3744))
- **agent-framework-core**: [BREAKING] Replace `Hosted*Tool` classes with tool methods ([#3634](https://github.com/microsoft/agent-framework/pull/3634))
- **agent-framework-core**: Replace Pydantic Settings with `TypedDict` + `load_settings()` ([#3843](https://github.com/microsoft/agent-framework/pull/3843))
- **agent-framework-core**: Centralize tool result parsing in `FunctionTool.invoke()` ([#3854](https://github.com/microsoft/agent-framework/pull/3854))
- **samples**: Restructure Python samples into progressive 01-05 layout ([#3862](https://github.com/microsoft/agent-framework/pull/3862))
- **samples**: Adopt `AzureOpenAIResponsesClient`, reorganize orchestration examples, and fix workflow/orchestration bugs ([#3873](https://github.com/microsoft/agent-framework/pull/3873))

### Fixed

- **agent-framework-core**: Fix non-ascii chars in span attributes ([#3894](https://github.com/microsoft/agent-framework/pull/3894))
- **agent-framework-core**: Fix streamed workflow agent continuation context by finalizing `AgentExecutor` streams ([#3882](https://github.com/microsoft/agent-framework/pull/3882))
- **agent-framework-ag-ui**: Fix `Workflow.as_agent()` streaming regression ([#3875](https://github.com/microsoft/agent-framework/pull/3875))
- **agent-framework-declarative**: Fix declarative package powerfx import crash and `response_format` kwarg error ([#3841](https://github.com/microsoft/agent-framework/pull/3841))

## [1.0.0b260210] - 2026-02-10

### Added

- **agent-framework-core**: Add long-running agents and background responses support with `ContinuationToken` TypedDict, `background` option in `OpenAIResponsesOptions`, and continuation token propagation through response types ([#3808](https://github.com/microsoft/agent-framework/pull/3808))
- **agent-framework-core**: Add streaming support for code interpreter deltas ([#3775](https://github.com/microsoft/agent-framework/pull/3775))
- **agent-framework-core**: Add explicit input, output, and workflow_output parameters to `@handler`, `@executor` and `request_info` ([#3472](https://github.com/microsoft/agent-framework/pull/3472))
- **agent-framework-core**: Add explicit schema handling to `@tool` decorator ([#3734](https://github.com/microsoft/agent-framework/pull/3734))
- **agent-framework-core**: New session and context provider types ([#3763](https://github.com/microsoft/agent-framework/pull/3763))
- **agent-framework-purview**: Add tests to Purview package ([#3513](https://github.com/microsoft/agent-framework/pull/3513))

### Changed

- **agent-framework-core**: [BREAKING] Renamed core types for simpler API: `ChatAgent` → `Agent`, `RawChatAgent` → `RawAgent`, `ChatMessage` → `Message`, `ChatClientProtocol` → `SupportsChatGetResponse` ([#3747](https://github.com/microsoft/agent-framework/pull/3747))
- **agent-framework-core**: [BREAKING] Moved to a single `get_response` and `run` API ([#3379](https://github.com/microsoft/agent-framework/pull/3379))
- **agent-framework-core**: [BREAKING] Merge `send_responses` into `run` method ([#3720](https://github.com/microsoft/agent-framework/pull/3720))
- **agent-framework-core**: [BREAKING] Renamed `AgentRunContext` to `AgentContext` ([#3714](https://github.com/microsoft/agent-framework/pull/3714))
- **agent-framework-core**: [BREAKING] Renamed `AgentProtocol` to `SupportsAgentRun` ([#3717](https://github.com/microsoft/agent-framework/pull/3717))
- **agent-framework-core**: [BREAKING] Renamed next middleware parameter to `call_next` ([#3735](https://github.com/microsoft/agent-framework/pull/3735))
- **agent-framework-core**: [BREAKING] Standardize TypeVar naming convention (`TName` → `NameT`) ([#3770](https://github.com/microsoft/agent-framework/pull/3770))
- **agent-framework-core**: [BREAKING] Refactor workflow events to unified discriminated union pattern ([#3690](https://github.com/microsoft/agent-framework/pull/3690))
- **agent-framework-core**: [BREAKING] Refactor `SharedState` to `State` with sync methods and superstep caching ([#3667](https://github.com/microsoft/agent-framework/pull/3667))
- **agent-framework-core**: [BREAKING] Move single-config fluent methods to constructor parameters ([#3693](https://github.com/microsoft/agent-framework/pull/3693))
- **agent-framework-core**: [BREAKING] Types API Review improvements ([#3647](https://github.com/microsoft/agent-framework/pull/3647))
- **agent-framework-core**: [BREAKING] Fix workflow as agent streaming output ([#3649](https://github.com/microsoft/agent-framework/pull/3649))
- **agent-framework-orchestrations**: [BREAKING] Move orchestrations to dedicated package ([#3685](https://github.com/microsoft/agent-framework/pull/3685))
- **agent-framework-core**: [BREAKING] Remove workflow register factory methods; update tests and samples ([#3781](https://github.com/microsoft/agent-framework/pull/3781))
- **agent-framework-core**: Include sub-workflow structure in graph signature for checkpoint validation ([#3783](https://github.com/microsoft/agent-framework/pull/3783))
- **agent-framework-core**: Adjust workflows TypeVars from prefix to suffix naming convention ([#3661](https://github.com/microsoft/agent-framework/pull/3661))
- **agent-framework-purview**: Update CorrelationId ([#3745](https://github.com/microsoft/agent-framework/pull/3745))
- **agent-framework-anthropic**: Added internal kwargs filtering for Anthropic client ([#3544](https://github.com/microsoft/agent-framework/pull/3544))
- **agent-framework-github-copilot**: Updated instructions/system_message logic in GitHub Copilot agent ([#3625](https://github.com/microsoft/agent-framework/pull/3625))
- **agent-framework-mem0**: Disable mem0 telemetry by default ([#3506](https://github.com/microsoft/agent-framework/pull/3506))

### Fixed

- **agent-framework-core**: Fix workflow not pausing when agent calls declaration-only tool ([#3757](https://github.com/microsoft/agent-framework/pull/3757))
- **agent-framework-core**: Fix GroupChat orchestrator message cleanup issue ([#3712](https://github.com/microsoft/agent-framework/pull/3712))
- **agent-framework-core**: Fix HandoffBuilder silently dropping `context_provider` during agent cloning ([#3721](https://github.com/microsoft/agent-framework/pull/3721))
- **agent-framework-core**: Fix subworkflow duplicate request info events ([#3689](https://github.com/microsoft/agent-framework/pull/3689))
- **agent-framework-core**: Fix workflow cancellation not propagating to active executors ([#3663](https://github.com/microsoft/agent-framework/pull/3663))
- **agent-framework-core**: Filter `response_format` from MCP tool call kwargs ([#3494](https://github.com/microsoft/agent-framework/pull/3494))
- **agent-framework-core**: Fix broken Content API imports in Python samples ([#3639](https://github.com/microsoft/agent-framework/pull/3639))
- **agent-framework-core**: Potential fix for clear-text logging of sensitive information ([#3573](https://github.com/microsoft/agent-framework/pull/3573))
- **agent-framework-core**: Skip `model_deployment_name` validation for application endpoints ([#3621](https://github.com/microsoft/agent-framework/pull/3621))
- **agent-framework-azure-ai**: Fix AzureAIClient dropping agent instructions (Responses API) ([#3636](https://github.com/microsoft/agent-framework/pull/3636))
- **agent-framework-azure-ai**: Fix AzureAIAgentClient dropping agent instructions in sequential workflows ([#3563](https://github.com/microsoft/agent-framework/pull/3563))
- **agent-framework-ag-ui**: Fix AG-UI message handling and MCP tool double-call bug ([#3635](https://github.com/microsoft/agent-framework/pull/3635))
- **agent-framework-claude**: Handle API errors in `run_stream()` method ([#3653](https://github.com/microsoft/agent-framework/pull/3653))
- **agent-framework-claude**: Preserve `$defs` in JSON schema for nested Pydantic models ([#3655](https://github.com/microsoft/agent-framework/pull/3655))

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
- **agent-framework-core**: [BREAKING] Standardize orchestration outputs as list of `Message`; allow agent as group chat manager (#2291)
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
- **agent-framework-core**: Langfuse observability captures Agent system instructions ([#2316](https://github.com/microsoft/agent-framework/pull/2316))
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

[Unreleased]: https://github.com/microsoft/agent-framework/compare/python-1.1.0...HEAD
[1.1.0]: https://github.com/microsoft/agent-framework/compare/python-1.0.1...python-1.1.0
[1.0.1]: https://github.com/microsoft/agent-framework/compare/python-1.0.0...python-1.0.1
[1.0.0]: https://github.com/microsoft/agent-framework/compare/python-1.0.0rc6...python-1.0.0
[1.0.0rc6]: https://github.com/microsoft/agent-framework/compare/python-1.0.0rc5...python-1.0.0rc6
[1.0.0rc5]: https://github.com/microsoft/agent-framework/compare/python-1.0.0rc4...python-1.0.0rc5
[1.0.0rc4]: https://github.com/microsoft/agent-framework/compare/python-1.0.0rc3...python-1.0.0rc4
[1.0.0rc3]: https://github.com/microsoft/agent-framework/compare/python-1.0.0rc2...python-1.0.0rc3
[1.0.0rc2]: https://github.com/microsoft/agent-framework/compare/python-1.0.0rc1...python-1.0.0rc2
[1.0.0rc1]: https://github.com/microsoft/agent-framework/compare/python-1.0.0b260212...python-1.0.0rc1
[1.0.0b260212]: https://github.com/microsoft/agent-framework/compare/python-1.0.0b260210...python-1.0.0b260212
[1.0.0b260210]: https://github.com/microsoft/agent-framework/compare/python-1.0.0b260130...python-1.0.0b260210
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
