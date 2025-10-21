# Changelog

All notable changes to the Agent Framework Python packages will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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

[Unreleased]: https://github.com/microsoft/agent-framework/compare/python-1.0.0b251016...HEAD
[1.0.0b251016]: https://github.com/microsoft/agent-framework/compare/python-1.0.0b251007...python-1.0.0b251016
[1.0.0b251007]: https://github.com/microsoft/agent-framework/compare/python-1.0.0b251001...python-1.0.0b251007
[1.0.0b251001]: https://github.com/microsoft/agent-framework/releases/tag/python-1.0.0b251001
