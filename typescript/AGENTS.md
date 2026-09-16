# TypeScript SDK

The TypeScript implementation is an npm workspace targeting Node.js 22.12 and later.

## Structure

- `packages/core` contains provider-neutral messages, agents, sessions, middleware, tools, and the function-calling loop.
- `packages/openai` contains the OpenAI Chat Completions adapter.
- `samples` contains compile-checked examples.

Provider packages depend on the public exports of `@microsoft/agent-framework-core`; they must not import another package's private source files.

## Commands

Run these commands from `typescript/`:

```bash
npm ci
npm run check
```

Use `npm run format` before submitting changes. Tests must not require live credentials or network access.

## Conventions

- Use strict TypeScript and preserve `exactOptionalPropertyTypes` and `noUncheckedIndexedAccess`.
- Keep provider wire formats out of the core package.
- Require explicit JSON Schema for function tools because TypeScript types are erased at runtime.
- Keep streaming and non-streaming behavior equivalent, especially function-call/result ordering and exactly-once execution.
- Add focused tests for every public behavior change.
