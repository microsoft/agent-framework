# Changelog

All notable changes to the Agent Framework Python packages will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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

[Unreleased]: https://github.com/microsoft/agent-framework/compare/python-1.0.0b251112.post1...HEAD
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
