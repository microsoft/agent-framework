# IMPLREADME Phase 3: Documentation and Migration Guide

**Source**: `.designs/1/implementation-plan/implementation_plan_outline.md`
**Phase**: 3 of 3
**Recommended Skill**: `manual`

## Objective

Create migration guide and expand XML doc comments for auto-yield/send behavior, naming clarifications, and method-level attribute scope.

## Changes Made

1. **MIGRATION.md** — step-by-step guide for converting from `ReflectingExecutor<T>` to `[MessageHandler]` pattern
2. **ExecutorOptions.cs** — expanded XML doc remarks for `AutoSendMessageHandlerResultObject` and `AutoYieldOutputHandlerResultObject`
3. **YieldsOutputAttribute.cs** — naming clarification (YieldsOutput vs YieldsMessage)
4. **SendsMessageAttribute.cs** — method-level scope note (no effect on non-handler methods)
5. **MessageHandlerAttribute.cs** — runtime dependency on AutoYield/AutoSend options
