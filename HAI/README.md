# AGORA HAI (Human Agent Interface)

A modern React-based web application that provides inspectors with an intuitive interface to interact with the AGORA multi-agent system via text and voice.

## Features

- **Real-time Chat Interface**: Text-based communication with the AGORA orchestrator
- **Voice Interface**: Voice input with visual feedback and audio visualization
- **Tool Approval Workflow**: Secure approval system for agent tool executions
- **WebSocket Communication**: Real-time bidirectional communication using the HAI Protocol
- **Accessibility First**: WCAG 2.1 AA compliant with full keyboard navigation and screen reader support
- **Modern UI**: Built with shadcn/ui and Tailwind CSS for a beautiful, responsive experience

## Tech Stack

- **React 18+** with TypeScript 5+
- **Vite** for fast development and optimized builds
- **Zustand** for state management
- **Zod** for runtime type validation
- **shadcn/ui** component library
- **Tailwind CSS** for styling
- **Vitest** for testing

## Prerequisites

- Node.js 20+
- pnpm 8+

## Installation

```bash
cd HAI
pnpm install
```

## Configuration

Create a `.env.local` file based on `.env.example`:

```bash
cp .env.example .env.local
```

Edit `.env.local` with your configuration:

```env
VITE_WS_URL=ws://localhost:8000/ws
VITE_OPENAI_API_KEY=your_api_key_here
VITE_APP_NAME=AGORA HAI
VITE_SESSION_TIMEOUT=3600000
```

## Development

Start the development server:

```bash
pnpm run dev
```

The application will be available at `http://localhost:3000`.

## Building

Create a production build:

```bash
pnpm run build
```

Preview the production build:

```bash
pnpm run preview
```

## Testing

Run tests:

```bash
pnpm run test
```

Run tests in watch mode:

```bash
pnpm run test:watch
```

Generate coverage report:

```bash
pnpm run test:coverage
```

## Code Quality

Lint code:

```bash
pnpm run lint
```

Fix linting issues:

```bash
pnpm run lint:fix
```

Type check:

```bash
pnpm run type-check
```

## Project Structure

```
HAI/
├── src/
│   ├── components/       # React components
│   │   ├── ui/          # shadcn/ui components
│   │   ├── chat/        # Chat interface components
│   │   ├── voice/       # Voice interface components
│   │   ├── approval/    # Tool approval components
│   │   └── layout/      # Layout components
│   ├── hooks/           # Custom React hooks
│   ├── lib/             # Utilities and libraries
│   │   ├── websocket/   # WebSocket client
│   │   └── utils/       # Utility functions
│   ├── stores/          # Zustand stores
│   ├── styles/          # Global styles
│   ├── types/           # TypeScript types and schemas
│   ├── App.tsx          # Main App component
│   └── main.tsx         # Application entry point
├── tests/               # Test files
└── public/              # Static assets
```

## HAI Protocol

The application communicates with the AGORA orchestrator using the HAI Protocol over WebSocket. The protocol supports the following message types:

- `user_message`: User input to orchestrator
- `assistant_message`: Response from orchestrator
- `tool_approval_request`: Request user approval for tool execution
- `tool_approval_response`: User's approval decision
- `status`: Status updates (thinking, routing, executing_tools, completed)
- `error`: Error messages

See `src/types/schemas.ts` for detailed message schemas.

## Accessibility

The application is designed with accessibility in mind:

- ✅ Keyboard navigation support
- ✅ ARIA labels and roles
- ✅ Screen reader friendly
- ✅ Focus management
- ✅ Color contrast compliance
- ✅ Semantic HTML

## Browser Support

- Chrome/Edge 90+
- Firefox 88+
- Safari 14+

## Docker

Build the Docker image:

```bash
docker build -t agora-hai .
```

Run the container:

```bash
docker run -p 80:80 agora-hai
```

## Contributing

1. Follow the TypeScript and React conventions outlined in `.cursor/hai-react-app.mdc`
2. Ensure all tests pass before submitting changes
3. Maintain accessibility standards
4. Write meaningful commit messages following conventional commits

## License

Proprietary - AGORA Development Team

## Support

For issues or questions, contact the AGORA Development Team.

