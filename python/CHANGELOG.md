# Changelog

All notable changes to the Agent Framework Python packages will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Introducing AI Function approval ([#1131](https://github.com/microsoft/agent-framework/pull/1131))
- Add name and description to workflows ([#1183](https://github.com/microsoft/agent-framework/pull/1183))
- Add Ollama example using OpenAIChatClient ([#1100](https://github.com/microsoft/agent-framework/pull/1100))
- Add DevUI improvements with color scheme, linking, agent details, and token usage data ([#1091](https://github.com/microsoft/agent-framework/pull/1091))
- Add semantic-kernel to agent-framework migration code samples ([#1045](https://github.com/microsoft/agent-framework/pull/1045))
- Add metapackage metadata stub to restore flit builds ([#1043](https://github.com/microsoft/agent-framework/pull/1043))

### Changed
- Update References to Agent2Agent protocol to use correct terminology ([#1162](https://github.com/microsoft/agent-framework/pull/1162))
- Update getting started samples to reflect AF and update unit test ([#1093](https://github.com/microsoft/agent-framework/pull/1093))
- Update README with links to video content and initial code samples as quickstart ([#1049](https://github.com/microsoft/agent-framework/pull/1049))
- Update Lab Installation instructions to install from source ([#1051](https://github.com/microsoft/agent-framework/pull/1051))
- Update python DEV_SETUP to add brew-based uv installation ([#1173](https://github.com/microsoft/agent-framework/pull/1173))
- Update docstrings of all files and add example code in public interfaces ([#1107](https://github.com/microsoft/agent-framework/pull/1107))
- Clarifications on installing packages in README ([#1036](https://github.com/microsoft/agent-framework/pull/1036))
- DevUI Fixes ([#1035](https://github.com/microsoft/agent-framework/pull/1035))
- Packaging fixes: removed lab from dependencies, setup build/publish tasks, set homepage url ([#1056](https://github.com/microsoft/agent-framework/pull/1056))
- Agents + Chat Client Samples Docstring Updates ([#1028](https://github.com/microsoft/agent-framework/pull/1028))
- Python: Foundry Agent Completeness ([#954](https://github.com/microsoft/agent-framework/pull/954))

### Fixed
- Fix MCP tool calls to flatten nested JSON arguments (handle $ref schemas) ([#990](https://github.com/microsoft/agent-framework/pull/990))
- Fix PyPI version strings to comply with PEP 440 ([#1040](https://github.com/microsoft/agent-framework/pull/1040))
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

[Unreleased]: https://github.com/microsoft/agent-framework/compare/python-1.0.0b251001...HEAD
[1.0.0b251001]: https://github.com/microsoft/agent-framework/releases/tag/python-1.0.0b251001
