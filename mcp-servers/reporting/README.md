# HAP Inspectierapport Automatisering Server

Geautomatiseerde generatie van HAP (Hygiëne en ARBO Protocol) inspectierapporten voor NVWA-inspecteurs met behulp van gespreksanalyse en gestructureerde data-extractie.

## Overzicht

Deze MCP server analyseert inspectiegesprekken, haalt gestructureerde HAP-formuliergegevens op, verifieert ontbrekende informatie met inspecteurs, en genereert uitgebreide rapporten in zowel JSON- als PDF-formaat.

## Functionaliteiten

- **Gespreksanalyse**: Gebruikt GPT-4 om inspectiegegevens te extraheren uit natuurlijke taalgesprekken
- **Gestructureerde Data-extractie**: Mapt bevindingen uit gesprekken naar de officiële HAP-formulierstructuur
- **Slimme Verificatie**: Identificeert ontbrekende/onzekere velden en genereert verduidelijkende vragen
- **Dubbel Formaat Rapporten**: Genereert zowel JSON (voor systemen) als PDF (voor mensen)
- **Bestandsopslag**: Tijdelijk sessiebeheer met georganiseerde bestandsstructuur
- **Betrouwbaarheidsscore**: Houdt betrouwbaarheidsniveaus bij voor alle geëxtraheerde velden

## MCP Tools

### 1. `start_inspection_report`
Initialiseer een nieuwe HAP inspectierapportsessie.

### 2. `extract_inspection_data`
Extraheer gestructureerde HAP-gegevens uit gespreksgeschiedenis.

### 3. `verify_inspection_data`
Genereer verificatievragen voor ontbrekende velden.

### 4. `submit_verification_answers`
Verwerk antwoorden van de inspecteur op verificatievragen.

### 5. `generate_final_report`
Maak definitieve JSON en PDF rapporten.

### 6. `get_report_status`
Controleer de voltooiing en status van het rapport.

## Workflow

### Fase 1: Data-extractie
1. Inspecteur voltooit inspectiegesprek
2. Systeem roept `extract_inspection_data` aan met volledige gespreksgeschiedenis
3. AI extraheert alle bekende HAP-velden met betrouwbaarheidsscores
4. Retourneert conceptgegevens + velden die verificatie nodig hebben

### Fase 2: Verificatie
1. Systeem roept `verify_inspection_data` aan met conceptgegevens
2. AI genereert 3-5 gerichte vragen voor ontbrekende kritieke velden
3. Inspecteur antwoordt via chatinterface
4. Systeem roept `submit_verification_answers` aan om concept bij te werken

### Fase 3: Generatie
1. Systeem roept `generate_final_report` aan
2. Generator maakt gestructureerde JSON die overeenkomt met HAP-schema
3. Generator maakt opgemaakte PDF met alle secties
4. Beide bestanden opgeslagen in `storage/{session_id}/`
5. Retourneert downloadlinks en samenvatting

## HAP Rapportstructuur

### Categorieën:
- **Hygiëne Algemeen**: Schoonmaak, faciliteiten, apparatuur
- **Ongediertebestrijding**: Preventie en bestrijding
- **Veilig Omgaan met Voedsel**: Voedselveiligheid, opslag, temperaturen
- **Allergeneninformatie**: Etikettering en informatie
- **Aanvullende Informatie**: Notities inspecteur, hygiënecodes, herhaalde overtredingen

### Ernst van Overtreding:
- **Ernstige overtreding**: Direct gevaar voor voedselveiligheid
- **Overtreding**: Hygiënetekortkomingen
- **Geringe overtreding**: Kleine problemen

## Opslagstructuur

```
storage/
├── reports/
│   └── {session_id}/
│       ├── draft_data.json
│       ├── final_report.json
│       └── final_report.pdf
└── conversation_history/
    └── {session_id}.json
```

## Afhankelijkheden

- **pydantic**: Datavalidatie en schema-afdwinging
- **openai**: GPT-4 voor gespreksanalyse
- **reportlab**: PDF-generatie
- **fastmcp**: MCP server framework

## Configuratie

Stel de volgende omgevingsvariabele in:

```bash
export OPENAI_API_KEY="jouw-openai-api-key"
```

## Draaien

### Met Docker
```bash
docker build -t mcp-reporting .
docker run -p 8000:8000 -e OPENAI_API_KEY=$OPENAI_API_KEY mcp-reporting
```

### Lokaal
```bash
pip install -r requirements.txt
export OPENAI_API_KEY="jouw-sleutel"
python server.py
```

## Integratie met AGORA

De rapportage-agent gebruikt deze tools automatisch wanneer inspecteurs rapportgeneratie aanvragen:

**Trigger zinnen:**
- "Genereer rapport"
- "Maak inspectierapport"
- "Finaliseer documentatie"
- "Rond inspectie af"

## Toekomstige Verbeteringen

- Database opslag (PostgreSQL/Supabase)
- Afhandeling van foto/bewijsmateriaal bijlagen
- Digitale handtekening integratie
- Meertalige ondersteuning (Nederlands/Engels)
- Offline modus ondersteuning

## Licentie

Intern NVWA/AGORA project
