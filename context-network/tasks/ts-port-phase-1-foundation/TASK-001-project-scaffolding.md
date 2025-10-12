# Task: TASK-001 Project Scaffolding & Configuration

**Phase**: 1
**Priority**: Critical
**Estimated Effort**: 3 hours
**Dependencies**: None

## Objective
Set up TypeScript project structure with build tools, linting, testing framework, and initial configuration files.

## Context References
- **Spec Section**: 002-typescript-feature-parity.md § Non-Functional Requirements (NFR-1 to NFR-8)
- **Python Reference**: `/python/pyproject.toml` (configuration patterns)
- **Standards**: CLAUDE.md § Development Commands

## Files to Create
- `package.json` - Project metadata and scripts
- `tsconfig.json` - TypeScript compiler configuration
- `tsconfig.build.json` - Build-specific config
- `eslint.config.js` - Linting rules
- `vitest.config.ts` - Test configuration
- `.prettierrc` - Code formatting
- `.gitignore` - Git exclusions
- `src/index.ts` - Main entry point
- `README.md` - Getting started guide

## Implementation Requirements

### Package Configuration (`package.json`)
1. Package name: `@microsoft/agent-framework-ts`
2. TypeScript 5.3+ as dev dependency
3. Vitest for testing with coverage support (@vitest/coverage-v8)
4. ESLint with TypeScript parser (@typescript-eslint/parser, @typescript-eslint/eslint-plugin)
5. Prettier for code formatting
6. Build scripts:
   - `build`: `tsc -p tsconfig.build.json`
   - `test`: `vitest run`
   - `test:watch`: `vitest`
   - `test:coverage`: `vitest run --coverage`
   - `lint`: `eslint src`
   - `lint:fix`: `eslint src --fix`
   - `format`: `prettier --write src`
   - `format:check`: `prettier --check src`
7. Main entry: `dist/index.js`
8. Types entry: `dist/index.d.ts`
9. Files: `["dist"]`

### TypeScript Configuration (`tsconfig.json`)
1. Strict mode enabled (`strict: true`)
2. Target: `ES2022`
3. Module: `ESNext`
4. Module resolution: `Bundler`
5. Declaration files generated (`declaration: true`)
6. Source maps enabled (`sourceMap: true`)
7. Output directory: `dist`
8. Include: `["src/**/*"]`
9. Exclude: `["node_modules", "dist", "**/*.test.ts"]`
10. Additional strict flags:
    - `noUnusedLocals: true`
    - `noUnusedParameters: true`
    - `noImplicitReturns: true`
    - `noFallthroughCasesInSwitch: true`

### Build Config (`tsconfig.build.json`)
1. Extends `tsconfig.json`
2. Exclude: `["**/*.test.ts", "**/__tests__/**"]`

### Linting Configuration (`eslint.config.js`)
1. Use flat config format (ESLint 9+)
2. TypeScript ESLint parser
3. Recommended TypeScript rules
4. Rules:
   - `@typescript-eslint/no-explicit-any`: `error` (require justification comment to disable)
   - `@typescript-eslint/explicit-function-return-type`: `warn`
   - `@typescript-eslint/no-unused-vars`: `error`
   - `max-len`: `["error", { "code": 120 }]`
5. Ignore patterns: `dist`, `node_modules`, `coverage`

### Testing Configuration (`vitest.config.ts`)
1. Coverage threshold: 80% lines
2. Include pattern: `**/*.test.ts`
3. Coverage reporters: `text`, `html`, `lcov`
4. Coverage provider: `v8`
5. Coverage exclude:
   - `**/*.test.ts`
   - `**/__tests__/**`
   - `**/index.ts` (re-export files)
6. Globals: `true` (for describe, it, expect without imports)

### Prettier Configuration (`.prettierrc`)
1. Print width: 120
2. Single quotes: true
3. Trailing comma: `all`
4. Arrow parens: `always`
5. Semi: true

### Git Ignore (`.gitignore`)
```
node_modules/
dist/
coverage/
*.log
.DS_Store
.env
.env.local
```

### Initial Entry Point (`src/index.ts`)
```typescript
/**
 * Microsoft Agent Framework for TypeScript
 *
 * A framework for building, orchestrating, and deploying AI agents.
 */

export const version = '0.1.0';
```

### README Template
Include:
1. Project description
2. Installation: `npm install @microsoft/agent-framework-ts`
3. Quick start example (placeholder)
4. Development setup:
   - `npm install`
   - `npm test`
   - `npm run build`
5. Links to documentation
6. License (MIT)

## Test Requirements
- Create `src/__tests__/setup.test.ts` with sample test:
  ```typescript
  import { describe, it, expect } from 'vitest';
  import { version } from '../index';

  describe('Project Setup', () => {
    it('should export version', () => {
      expect(version).toBe('0.1.0');
    });
  });
  ```
- Test passes: `npm test`
- Coverage report generates: `npm run test:coverage`
- Linting passes: `npm run lint`
- Build succeeds: `npm run build`

**Minimum Coverage**: N/A (no implementation yet)

## Acceptance Criteria
- [ ] `npm install` completes successfully
- [ ] `npm run build` produces `dist/` with JS and declaration files
- [ ] `npm test` runs and passes sample test
- [ ] `npm run lint` passes with no errors
- [ ] `npm run format:check` passes
- [ ] TypeScript strict mode enabled
- [ ] Coverage reporting configured and working
- [ ] README includes setup instructions
- [ ] All config files validated (valid JSON/JS)

## Example Code Pattern

**package.json scripts section**:
```json
{
  "scripts": {
    "build": "tsc -p tsconfig.build.json",
    "test": "vitest run",
    "test:watch": "vitest",
    "test:coverage": "vitest run --coverage",
    "lint": "eslint src",
    "lint:fix": "eslint src --fix",
    "format": "prettier --write src",
    "format:check": "prettier --check src"
  }
}
```

**eslint.config.js** (flat config):
```javascript
import tseslint from '@typescript-eslint/eslint-plugin';
import tsparser from '@typescript-eslint/parser';

export default [
  {
    files: ['src/**/*.ts'],
    languageOptions: {
      parser: tsparser,
      parserOptions: {
        project: './tsconfig.json',
      },
    },
    plugins: {
      '@typescript-eslint': tseslint,
    },
    rules: {
      '@typescript-eslint/no-explicit-any': 'error',
      '@typescript-eslint/explicit-function-return-type': 'warn',
      'max-len': ['error', { code: 120 }],
    },
  },
];
```

## Related Tasks
- **Blocks**: ALL Phase 1 tasks (001-013)
- **Blocked by**: None
- **Related**: None
