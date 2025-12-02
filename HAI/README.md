# AGORA HAI (Human Agent Interface)

Een moderne, op React gebaseerde webapplicatie die inspecteurs een intuïtieve interface biedt voor interactie met het AGORA multi-agent systeem via tekst en spraak.

## Functionaliteiten

- **Real-time Chat Interface**: Tekstgebaseerde communicatie met de AGORA orchestrator
- **Spraakinterface**: Spraakinvoer met visuele feedback en audiovisualisatie
- **Tool Goedkeuringsworkflow**: Veilig goedkeuringssysteem voor het uitvoeren van agent-tools
- **WebSocket Communicatie**: Real-time bidirectionele communicatie met behulp van het AG-UI Protocol
- **Toegankelijkheid Eerst**: Voldoet aan WCAG 2.1 AA met volledige toetsenbordnavigatie en ondersteuning voor schermlezers
- **Moderne UI**: Gebouwd met shadcn/ui en Tailwind CSS voor een mooie, responsieve ervaring

## Tech Stack

- **React 18+** met TypeScript 5+
- **Vite** voor snelle ontwikkeling en geoptimaliseerde builds
- **Zustand** voor state management
- **Zod** voor runtime type validatie
- **shadcn/ui** componentenbibliotheek
- **Tailwind CSS** voor styling
- **Vitest** voor testen

## Vereisten

- Node.js 20+
- pnpm 8+

## Installatie

```bash
cd HAI
pnpm install
```

## Configuratie

Maak een `.env.local` bestand op basis van `.env.example`:

```bash
cp .env.example .env.local
```

Pas `.env.local` aan met je configuratie:

```env
VITE_WS_URL=ws://localhost:8000/ws
VITE_OPENAI_API_KEY=jouw_api_key_hier
VITE_APP_NAME=AGORA HAI
VITE_SESSION_TIMEOUT=3600000
```

## Ontwikkeling

Start de ontwikkelserver:

```bash
pnpm run dev
```

De applicatie is beschikbaar op `http://localhost:3000`.

## Bouwen

Maak een productiebuild:

```bash
pnpm run build
```

Bekijk de productiebuild:

```bash
pnpm run preview
```

## Testen

Voer tests uit:

```bash
pnpm run test
```

Testen in watch modus:

```bash
pnpm run test:watch
```

Genereer coverage rapport:

```bash
pnpm run test:coverage
```

## Code Kwaliteit

Lint code:

```bash
pnpm run lint
```

Herstel linting problemen:

```bash
pnpm run lint:fix
```

Type check:

```bash
pnpm run type-check
```

## Projectstructuur

```
HAI/
├── src/
│   ├── components/       # React componenten
│   │   ├── ui/          # shadcn/ui componenten
│   │   ├── chat/        # Chat interface componenten
│   │   ├── voice/       # Spraak interface componenten
│   │   ├── approval/    # Tool goedkeuringscomponenten
│   │   └── layout/      # Layout componenten
│   ├── hooks/           # Aangepaste React hooks
│   ├── lib/             # Hulpprogramma's en bibliotheken
│   │   ├── websocket/   # WebSocket client
│   │   └── utils/       # Hulpfuncties
│   ├── stores/          # Zustand stores
│   ├── styles/          # Globale stijlen
│   ├── types/           # TypeScript types en schema's
│   ├── App.tsx          # Hoofd App component
│   └── main.tsx         # Applicatie toegangspunt
├── tests/               # Testbestanden
└── public/              # Statische assets
```

## AG-UI Protocol

De applicatie communiceert met de AGORA orchestrator via het AG-UI Protocol over WebSocket. AG-UI is een open, event-gebaseerd protocol voor agent-gebruiker communicatie.

**Event Types:**
- **Lifecycle**: `RUN_STARTED`, `RUN_FINISHED`, `RUN_ERROR`, `STEP_STARTED`, `STEP_FINISHED`
- **Text Messages**: `TEXT_MESSAGE_START`, `TEXT_MESSAGE_CONTENT`, `TEXT_MESSAGE_END`
- **Tool Calls**: `TOOL_CALL_START`, `TOOL_CALL_ARGS`, `TOOL_CALL_END`, `TOOL_CALL_RESULT`
- **State**: `STATE_SNAPSHOT`, `STATE_DELTA`
- **Custom**: `CUSTOM` (voor HITL goedkeuringsflow)

Zie `src/types/schemas.ts` voor Zod schemas en `/docs/hai-contract/AG_UI_PROTOCOL.md` voor de volledige specificatie.

## Toegankelijkheid

De applicatie is ontworpen met toegankelijkheid in gedachten:

- ✅ Ondersteuning voor toetsenbordnavigatie
- ✅ ARIA labels en rollen
- ✅ Schermlezer vriendelijk
- ✅ Focus management
- ✅ Kleurcontrast conformiteit
- ✅ Semantische HTML

## Browser Ondersteuning

- Chrome/Edge 90+
- Firefox 88+
- Safari 14+

## Docker

Bouw de Docker image:

```bash
docker build -t agora-hai .
```

Draai de container:

```bash
docker run -p 80:80 agora-hai
```

## Bijdragen

1. Volg de TypeScript en React conventies zoals beschreven in `.cursor/hai-react-app.mdc`
2. Zorg ervoor dat alle tests slagen voordat je wijzigingen indient
3. Behoud de toegankelijkheidsstandaarden
4. Schrijf betekenisvolle commit-berichten volgens conventionele commits

## Licentie

Zie de hoofd-README voor licentie-informatie.

## Ondersteuning

Neem voor problemen of vragen contact op met het AGORA Ontwikkelteam.
