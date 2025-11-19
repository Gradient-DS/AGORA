# Inspectiegeschiedenis MCP Server

Mock inspectiegeschiedenis database voor AGORA demo. Biedt toegang tot historische inspectiegegevens inclusief overtredingen, vervolgacties en herhaalde overtredingen.

## Overzicht

Deze MCP server biedt een gesimuleerde inspectiegeschiedenis database met realistische testdata voor het testen van AGORA v1.0 scenario's. Het integreert met de KVK Lookup server om volledige bedrijfsprofielen te bieden.

**Poort**: 5005 (gemapt van container poort 8000)

## Beschikbare Tools

### 1. get_inspection_history
Haal volledige inspectiegeschiedenis op voor een bedrijf.

**Gebruik:** Beantwoord "Zijn er eerdere overtredingen bekend?" type vragen

### 2. get_company_violations
Haal alle overtredingen op over alle inspecties voor een bedrijf heen.

**Gebruik:** Identificeer patronen van niet-naleving

### 3. check_repeat_violation
Controleer of een overtredingscategorie eerder is voorgekomen.

**Veelvoorkomende Categorieën:**
- `hygiene_measures` (hygiënemaatregelen)
- `food_labeling` (voedseletikettering)
- `product_labeling` (productetikettering)
- `temperature_control` (temperatuurbeheersing)
- `pest_control` (ongediertebestrijding)
- `allergen_information` (allergeneninformatie)

**Gebruik:** Bepaal handhavingsescalatie voor recidivisten

### 4. get_follow_up_status
Haal status van vervolgacties op die vereist zijn uit eerdere inspecties.

**Gebruik:** Volg naleving van corrigerende maatregelen

### 5. search_inspections_by_inspector
Zoek inspecties uitgevoerd door een specifieke inspecteur.

## Demo Data

De server bevat realistische demodata voor 4 bedrijven die overeenkomen met de AGORA v1.0 scenario's:

### 1. Restaurant Bella Rosa (KVK: 59581883)
**Scenario:** Koen's horeca-inspectie
- **Geschiedenis:** 2 inspecties (2020, 2022)
- **Overtredingen:** Waarschuwing hygiënemaatregelen in 2022 (onopgelost)
- **Kernkenmerk:** Herhaalde overtreding klaar voor escalatie

### 2. SpeelgoedPlaza Den Haag (KVK: 12345678)
**Scenario:** Fatima's productveiligheidsinspectie
- **Geschiedenis:** 1 inspectie (2023)
- **Overtredingen:** Waarschuwing productetikettering (opgelost)
- **Kernkenmerk:** Toont goede naleving na waarschuwing

### 3. Slagerij de Boer (KVK: 87654321)
**Scenario:** Jan's slagerij-inspectie
- **Geschiedenis:** 2 inspecties (2019, 2021)
- **Overtredingen:** Waarschuwing voedseletikettering in 2021 (onopgelost, vervolgactie te laat)
- **Kernkenmerk:** Recidivist met achterstallige vervolgactie

### 4. Café Het Bruine Paard (KVK: 11223344)
**Extra demodata**
- **Geschiedenis:** 1 inspectie (2024)
- **Overtredingen:** Geen
- **Kernkenmerk:** Schoon dossier voor contrast

## Integratie met AGORA

Voeg de Inspectiegeschiedenis server toe aan de orchestrator configuratie:

```bash
# In server-openai/.env
APP_MCP_SERVERS=regulation=http://localhost:5002,reporting=http://localhost:5003,history=http://localhost:5005
```

## Use Cases in AGORA

### 1. Scenario Testen (Alle Persona's)
Elk inspecteursscenario vereist historische data:
- **Koen:** "Zijn er eerdere overtredingen bekend?"
- **Fatima:** "Zijn er eerder onveilige producten aangetroffen?"
- **Jan:** "Wat is er eerder geconstateerd?"

### 2. Detectie Herhaalde Overtreding
Automatisch patronen identificeren:
```
Inspecteur dicteert: "Ongeëtiketteerde producten in koeling"
Agent: [roept check_repeat_violation aan]
       "WAARSCHUWING: Dit is een herhaalde overtreding. 
        In november 2021 was er een soortgelijk probleem..."
```

## Ontwikkeling

### Lokaal Testen

```bash
cd mcp-servers/inspection-history
pip install -r requirements.txt
python server.py
```

### Docker Deployment

```bash
cd mcp-servers
docker-compose up inspection-history
```

## Monitoring

Alle tool-uitvoeringen worden gelogd. Bekijk logs:
```bash
docker-compose logs -f inspection-history
```

## Beveiliging

- **Input validatie:** KVK-nummers gevalideerd als 8-cijferige strings
- **Non-root gebruiker:** Container draait als gebruiker ID 1000
- **Read-only data:** Demodata is onveranderlijk
- **Geen externe aanroepen:** Alle data in-memory

## Versie

**Versie:** 1.0.0  
**Laatst Bijgewerkt:** 16 november 2025  
**Status:** Demo/Mock Data
