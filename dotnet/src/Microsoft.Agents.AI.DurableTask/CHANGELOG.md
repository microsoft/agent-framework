# Release History

## [Unreleased]

- Added support for durable workflows ([#4436](https://github.com/microsoft/agent-framework/pull/4436))

## v1.0.0-preview.260219.1

- [BREAKING] Changed ChatHistory and AIContext Providers to have pipeline semantics ([#3806](https://github.com/microsoft/agent-framework/pull/3806))
- Marked all `RunAsync<T>` overloads as `new`, added missing ones, and added support for primitives and arrays ([#3803](https://github.com/microsoft/agent-framework/pull/3803))
- Improve session cast error message quality and consistency ([#3973](https://github.com/microsoft/agent-framework/pull/3973))

## v1.0.0-preview.260212.1

- [BREAKING] Changed AIAgent.SerializeSession to AIAgent.SerializeSessionAsync ([#3879](https://github.com/microsoft/agent-framework/pull/3879))

## v1.0.0-preview.260209.1

- [BREAKING] Introduce Core method pattern for Session management methods on AIAgent ([#3699](https://github.com/microsoft/agent-framework/pull/3699))

## v1.0.0-preview.260205.1

- [BREAKING] Moved AgentSession.Serialize to AIAgent.SerializeSession ([#3650](https://github.com/microsoft/agent-framework/pull/3650))
- [BREAKING] Renamed serializedSession parameter to serializedState on DeserializeSessionAsync for consistency ([#3681](https://github.com/microsoft/agent-framework/pull/3681))

## v1.0.0-preview.260127.1

- [BREAKING] Renamed AgentThread to AgentSession ([#3430](https://github.com/microsoft/agent-framework/pull/3430))

## v1.0.0-preview.260108.1

- [BREAKING] Removed AgentThreadMetadata and used AgentSessionId directly instead ([#3067](https://github.com/microsoft/agent-framework/pull/3067))

## v1.0.0-preview.251219.1

- Filter empty `AIContent` from durable agent state responses ([#4670](https://github.com/microsoft/agent-framework/pull/4670))

## v1.0.0-preview.260311.1

### Changed

- Added TTL configuration for durable agent entities ([#2679](https://github.com/microsoft/agent-framework/pull/2679))
- Switch to new "Run" method name ([#2843](https://github.com/microsoft/agent-framework/pull/2843))

NOTE: Some of the above changes may have been part of earlier releases not mentioned in this file.

## v1.0.0-preview.251204.1

- Added orchestration ID to durable agent entity state ([#2137](https://github.com/microsoft/agent-framework/pull/2137))

## v1.0.0-preview.251125.1

- Added support for .NET 10 ([#2128](https://github.com/microsoft/agent-framework/pull/2128))

## v1.0.0-preview.251114.1

- Added friendly error message when running durable agent that isn't registered ([#2214](https://github.com/microsoft/agent-framework/pull/2214))

## v1.0.0-preview.251112.1

- Initial public release ([#1916](https://github.com/microsoft/agent-framework/pull/1916))
