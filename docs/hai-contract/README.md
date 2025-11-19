# AGORA HAI Protocol - Contract Documentatie

Deze directory bevat de volledige API-contractdocumentatie voor het HAI (Human Agent Interface) Protocol dat door AGORA wordt gebruikt.

## 📋 Inhoud

### Kern Documentatie

- **[HAI_PROTOCOL.md](./HAI_PROTOCOL.md)** - Uitgebreide leesbare protocolspecificatie
  - Berichttypes en formaten
  - Gespreksstromen (flows)
  - Foutafhandelingspatronen
  - Implementatiegids met codevoorbeelden
  - TypeScript type definities

- **[asyncapi.yaml](./asyncapi.yaml)** - Machine-leesbare AsyncAPI 3.0 specificatie
  - Formeel contract voor WebSocket API
  - Kan worden gebruikt met AsyncAPI tools voor:
    - Documentatiegeneratie
    - Contract testing
    - Client SDK generatie
    - Mock server creatie

- **[openapi.yaml](./openapi.yaml)** - OpenAPI 3.0 specificatie
  - Formeel contract voor REST API (History & Users)
  - Complementeert het WebSocket protocol
  - Definieert HTTP endpoints voor sessiegeschiedenis en gebruikersbeheer

### Schema's

- **[schemas/messages.json](./schemas/messages.json)** - JSON Schema definities
  - Alle berichttypeschema's
  - Kan worden gebruikt voor validatie
  - Compatibel met code generatie tools

### Voorbeelden

- **[examples/basic-conversation.json](./examples/basic-conversation.json)**
  - Eenvoudige V&A flow
  - Afhandeling van streaming responses
  - Vervolgvragen

- **[examples/tool-approval-flow.json](./examples/tool-approval-flow.json)**
  - Human-in-the-loop goedkeuringsworkflow
  - Uitvoering van risicovolle tools
  - Goedkeurings- en afwijzingspaden

- **[examples/error-handling.json](./examples/error-handling.json)**
  - Alle foutscenario's
  - Herstelstrategieën
  - Verbindingspatronen

## 🚀 Snel aan de slag

### Voor Frontend Ontwikkelaars

1. Lees [HAI_PROTOCOL.md](./HAI_PROTOCOL.md) voor volledige protocoldocumentatie
2. Kopieer TypeScript types uit de Implementatiegids sectie
3. Raadpleeg [examples/](./examples/) voor berichtstroompatronen
4. Gebruik [schemas/messages.json](./schemas/messages.json) voor validatie

### Voor API Contract Testing

1. Laad [asyncapi.yaml](./asyncapi.yaml) in [AsyncAPI Studio](https://studio.asyncapi.com)
2. Genereer documentatie of client SDK's
3. Gebruik met Microcks voor contract testing
4. Integreer met CI/CD voor contractvalidatie

## 🔌 Verbindingsdetails

### Endpoints

```
Development: ws://localhost:8000/ws
```

### Authenticatie

Momenteel geen authenticatie vereist. Toekomstige versies kunnen token-gebaseerde authenticatie bevatten.

### Sessiebeheer

- Client genereert UUID als `session_id`
- Opslaan in localStorage voor continuïteit van gesprekken
- Insluiten in alle berichten

## 📝 Overzicht Berichttypes

| Type | Richting | Doel |
|------|-----------|---------|
| `user_message` | Client → Server | Gebruikersinvoer |
| `assistant_message` | Server → Client | Volledig antwoord (niet-streaming) |
| `assistant_message_chunk` | Server → Client | Streaming antwoordfragment ⭐ |
| `tool_call` | Server → Client | Melding tool-uitvoering |
| `tool_approval_request` | Server → Client | Verzoek om toestemming voor tool |
| `tool_approval_response` | Client → Server | Goedkeuringsbeslissing van gebruiker |
| `status` | Server → Client | Verwerkingsstatus |
| `error` | Server → Client | Foutmelding |

## 🛠 Tools & Bronnen

### AsyncAPI Ecosysteem

- **[AsyncAPI Studio](https://studio.asyncapi.com)** - Online editor en visualizer
- **[AsyncAPI Generator](https://www.asyncapi.com/tools/generator)** - Genereer docs, code, tests
- **[Microcks](https://microcks.io/)** - Mock server en contract testing
- **[Spectral](https://stoplight.io/open-source/spectral)** - Linting en validatie

### Test Tools

- **[websocat](https://github.com/vi/websocat)** - CLI WebSocket client
  ```bash
  websocat ws://localhost:8000/ws
  ```
- **[wscat](https://github.com/websockets/wscat)** - Alternatieve CLI client
  ```bash
  wscat -c ws://localhost:8000/ws
  ```
- **Postman** - GUI met WebSocket ondersteuning

### Code Generatie

Genereer TypeScript types van JSON Schema:
```bash
npm install -g json-schema-to-typescript
json2ts schemas/messages.json > types.ts
```

## 📖 Documentatieversies

| Versie | Datum | Wijzigingen |
|---------|------|---------|
| 1.0.0 | 2025-11-17 | Initiële protocolspecificatie |

## 🤝 Integratie Checklist

Gebruik deze checklist bij het integreren van het HAI protocol:

### Vereiste Implementatie

- [ ] WebSocket verbinding naar `/ws`
- [ ] Generatie en opslag van Sessie ID
- [ ] Verzenden van gebruikersberichten
- [ ] Afhandelen van streaming chunks (samenvoegen op `message_id`)
- [ ] Mapping van statusindicatoren
- [ ] Weergave van foutmeldingen
- [ ] Herstel bij verbindingsverlies

### Aanbevolen Implementatie

- [ ] Meldingen van tool-uitvoering
- [ ] Human-in-the-loop goedkeurings UI
- [ ] Opnieuw verbinden met exponentiële backoff
- [ ] Berichtvalidatie met JSON Schema
- [ ] Correcte afhandeling van foutcodes
- [ ] Beheer van laadstatus

### Optionele Uitbreidingen

- [ ] Opslag van berichthistorie
- [ ] Typ-indicatoren
- [ ] Leesbevestigingen
- [ ] Reacties op berichten
- [ ] Ondersteuning voor rich media

## 📞 Ondersteuning

Voor vragen of problemen met het protocol:

- **Technische Vragen**: dev@nvwa.nl
- **Bug Reports**: Dien in via de project issue tracker
- **Protocol Wijzigingen**: Stel voor via RFC proces

## 📄 Licentie

Zie hoofd-README.

---

**Onderhouden door:** Gradient - NVWA  
**Laatst bijgewerkt:** 17 november 2025
