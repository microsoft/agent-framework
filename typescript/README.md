# Microsoft Agent Framework for TypeScript

A framework for building, orchestrating, and deploying AI agents in TypeScript.

## Overview

The Microsoft Agent Framework provides a comprehensive set of tools and abstractions for building production-ready AI agents. This TypeScript implementation brings feature parity with the Python and .NET versions, enabling cross-platform agent development.

## Installation

```bash
npm install @microsoft/agent-framework-ts
```

## Quick Start

```typescript
import { version } from '@microsoft/agent-framework-ts';

console.log(`Agent Framework version: ${version}`);
```

> Note: This is an initial release. More examples and features will be added as development progresses.

## Development Setup

### Prerequisites

- Node.js 18.0.0 or higher
- npm 9.0.0 or higher

### Installation

```bash
# Clone the repository
git clone https://github.com/microsoft/agent-framework.git
cd agent-framework/typescript

# Install dependencies
npm install

# Run tests
npm test

# Build the project
npm run build
```

### Available Scripts

- `npm run build` - Build the TypeScript project
- `npm test` - Run tests with Vitest
- `npm run test:watch` - Run tests in watch mode
- `npm run test:coverage` - Generate coverage report
- `npm run lint` - Lint the codebase
- `npm run lint:fix` - Lint and auto-fix issues
- `npm run format` - Format code with Prettier
- `npm run format:check` - Check code formatting

## Project Structure

```
typescript/
├── src/
│   ├── index.ts              # Main entry point
│   └── __tests__/            # Test files
├── dist/                     # Compiled output (generated)
├── coverage/                 # Coverage reports (generated)
├── package.json              # Project configuration
├── tsconfig.json             # TypeScript configuration
├── tsconfig.build.json       # Build-specific TypeScript config
├── eslint.config.js          # ESLint configuration
├── vitest.config.ts          # Vitest test configuration
└── .prettierrc               # Prettier formatting rules
```

## Code Quality

This project maintains high code quality standards:

- **TypeScript Strict Mode**: Enabled for maximum type safety
- **Test Coverage**: 80% minimum coverage threshold
- **Linting**: ESLint with TypeScript rules
- **Formatting**: Prettier with consistent style
- **Testing**: Vitest with comprehensive test suite

## Documentation

- [Microsoft Learn - Agent Framework](https://learn.microsoft.com/agent-framework/)
- [GitHub Repository](https://github.com/microsoft/agent-framework)
- [Design Documents](../docs/design/)
- [ADRs](../docs/decisions/)

## Contributing

We welcome contributions! Please see [CONTRIBUTING.md](../CONTRIBUTING.md) for guidelines.

### Development Workflow

1. Create a feature branch from `main`
2. Make your changes with tests
3. Ensure all quality checks pass:
   ```bash
   npm run lint
   npm run format:check
   npm test
   npm run build
   ```
4. Submit a pull request

## License

This project is licensed under the MIT License - see the [LICENSE](../LICENSE) file for details.

## Support

- [GitHub Issues](https://github.com/microsoft/agent-framework/issues)
- [Discord Community](https://discord.gg/b5zjErwbQM)
- [Microsoft Learn Documentation](https://learn.microsoft.com/agent-framework/)

## Related Projects

- [Python Implementation](../python/)
- [.NET Implementation](../dotnet/)
- [Workflow Samples](../workflow-samples/)
