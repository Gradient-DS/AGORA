workspace "AGORA v1.0 — Multi-Agent Systeem NVWA" {
  !identifiers hierarchical
  
  model {
    inspector = person "Inspecteur" "NVWA medewerker die AGORA gebruikt voor dagelijks werk"
    
    agora = softwareSystem "AGORA" "Multi-agent systeem voor ondersteuning van NVWA inspecteurs" {
      
      // Core containers
      hai = container "Human Agent Interface (HAI)" "React + Audio (Whisper, ElevenLabs)" "React" {
        description "Gebruikersinterface voor interactie met AGORA via tekst en spraak"
        tags "Frontend"
        
        // HAI components
        uiComponents = component "UI Components" "React componenten" "React" {
          description "Gebruikersinterface componenten voor chat, voice en visualisaties"
        }
        audioInterface = component "Audio Interface" "Whisper + ElevenLabs" "TypeScript" {
          description "Spraak-naar-tekst en tekst-naar-spraak conversie"
        }
        websocketClient = component "WebSocket Client" "WebSocket verbinding" "TypeScript" {
          description "Real-time communicatie met Orchestrator"
        }
        
        uiComponents -> websocketClient "Stuurt berichten via"
        audioInterface -> websocketClient "Streamt audio via"
      }
      
      orchestrator = container "Orchestrator" "LangGraph + LLM (GPT-5/Sonnet-4.5)" "Python" {
        description "Centrale orchestratie-engine met reasoning LLM, state management, MCP client, memory management, moderatie en tool selectie"
        tags "Backend"
        
        // Orchestrator components
        reasoningLLM = component "Reasoning LLM" "Closed-source LLM (GPT-5, Sonnet-4.5)" "LLM" {
          description "Krachtig LLM met goede reasoning kwaliteiten en function calling"
        }
        mcpClient = component "MCP Client" "Model Context Protocol client" "Python" {
          description "Communiceert met externe services via MCP standaard"
        }
        moderator = component "Moderator" "Guardrails-AI" "Python" {
          description "AI governance: controleert op hallucinaties, gevoelige inhoud en compliance"
        }
        toolSelector = component "Tool Selector" "Policy Engine + Context Collector" "Python" {
          description "Selecteert en activeert relevante MCP tools op basis van gebruiker, situatie en gebeurtenissen"
        }
        memoryManager = component "Memory Manager" "LangChain Memory" "Python" {
          description "Beheert conversatie context en geschiedenis voor de agent"
        }
        stateManager = component "State Manager" "LangGraph State + Checkpointer" "Python" {
          description "Beheert orchestratie state met checkpointing, human-in-the-loop interventie en rollback mogelijkheden"
        }
        auditLogger = component "Audit Logger" "OpenTelemetry logger" "Python" {
          description "Audit logging van alle orchestrator beslissingen (ontvangt events van alle componenten)"
        }
        
        stateManager -> memoryManager "Beheert conversatie state"
        stateManager -> reasoningLLM "Orkestreert agent loop"
        toolSelector -> reasoningLLM "Levert beschikbare tools"
        reasoningLLM -> mcpClient "Roept tools aan via"
        reasoningLLM -> moderator "Controleert output via"
      }
      
      toolCatalog = container "Tool Catalog" "MCP tool en resource configuratie database" "PostgreSQL" {
        description "Database met beschikbare MCP tools, resources en hun configuraties"
        tags "Database"
        
        // Tool Catalog components
        toolRegistry = component "Tool Registry" "MCP tool metadata en configuraties" "Database Table" {
          description "Catalogus van alle beschikbare MCP tools en resources met hun capabilities"
        }
        toolConfig = component "Tool Config" "Actieve tool configuraties" "Database Table" {
          description "Configuraties van actieve tools per gebruiker/context"
        }
      }
      
      userProfile = container "User Profile" "Gebruikersprofiel database" "PostgreSQL" {
        description "Database met gebruikersprofielen voor personalisatie"
        tags "Database"
        
        // User Profile components
        profileData = component "Profile Data" "Gebruiker basisgegevens" "Database Table" {
          description "Naam, rol, voorkeuren, permissies"
        }
        preferences = component "Preferences" "Gebruikersvoorkeuren" "Database Table" {
          description "Taal, notificaties, agent voorkeuren"
        }
        history = component "History" "Gebruikersgeschiedenis" "Database Table" {
          description "Interactie geschiedenis en context"
        }
      }
      
      visibility = container "Visibility" "Grafana + Prometheus + OpenTelemetry" "Observability Stack" {
        description "Monitoring, logging en observability van het gehele AGORA systeem"
        tags "Observability"
      }
      
      // Internal relationships
      hai -> orchestrator "HAI Protocol" "WebSocket/JSON"
      orchestrator -> userProfile "Haalt profiel op" "SQL"
      orchestrator -> toolCatalog "Beheert tools" "SQL"
      
      // Visibility relationships (internal only)
      orchestrator -> visibility "Traces & decisions" "OpenTelemetry"
      
      // Component-level external relationships
      // HAI components
      agora.hai.websocketClient -> orchestrator "Communiceert met" "WebSocket"
      agora.hai.websocketClient -> agora.orchestrator.stateManager "Stuurt requests naar" "WebSocket"
      
      // Orchestrator components to internal containers
      agora.orchestrator.toolSelector -> agora.toolCatalog "Vraagt tool configuraties op" "SQL"
      agora.orchestrator.toolSelector -> agora.userProfile "Leest profiel" "SQL"
      agora.orchestrator.auditLogger -> agora.visibility "Stuurt logs" "OpenTelemetry"
      
      // Tool Catalog components (accessed by Orchestrator)
      agora.orchestrator.toolSelector -> agora.toolCatalog.toolRegistry "Leest catalogus" "SQL"
      agora.orchestrator.toolSelector -> agora.toolCatalog.toolConfig "Beheert configuraties" "SQL"
      
      // User Profile components (accessed by Orchestrator)
      agora.orchestrator.toolSelector -> agora.userProfile.profileData "Leest profiel data" "SQL"
      agora.orchestrator.toolSelector -> agora.userProfile.preferences "Leest voorkeuren" "SQL"
      agora.orchestrator.toolSelector -> agora.userProfile.history "Schrijft geschiedenis" "SQL"
    }
    
    // External systems
    externalServices = softwareSystem "External Services" "Externe MCP servers (Rapportage, ARIA-A Scanner, E-nummer Database, etc.)" {
      description "Collectie van externe services die tools en resources via MCP protocol aanbieden"
    }
    
    // Relationships
    inspector -> agora "Gebruikt" "Tekst/Spraak/Video"
    inspector -> agora.hai "Interacteert met" "HTTPS/WebSocket"
    inspector -> agora.hai.uiComponents "Gebruikt interface" "HTTPS"
    inspector -> agora.hai.audioInterface "Spreekt met" "Audio"
    
    agora -> externalServices "Communiceert met services" "MCP Protocol"
    agora.orchestrator -> externalServices "Roept aan via MCP" "MCP Protocol"
    agora.orchestrator.mcpClient -> externalServices "Roept tools aan" "MCP"
  }
  
  views {
    systemContext agora "SystemContext" {
      include *
      description "System context diagram van AGORA v1.0 - Inspecteur gebruikt AGORA om met externe agents te communiceren"
    }
    
    container agora "Containers" {
      include inspector
      include agora.hai
      include agora.orchestrator
      include agora.userProfile  
      include agora.toolCatalog
      include agora.visibility
      include externalServices
      description "Container diagram van AGORA v1.0 - HAI, Orchestrator, User Profile en Tool Catalog databases met externe interacties"
    }
    
    component agora.orchestrator "OrchestratorComponents" {
      include *
      include agora.hai
      include agora.userProfile
      include agora.toolCatalog
      include agora.visibility
      include externalServices
      description "Component breakdown van de Orchestrator - State Manager, Reasoning LLM, Memory Manager, MCP Client, Moderator, Tool Selector, Audit Logger"
    }
    
    component agora.hai "HAIComponents" {
      include *
      include inspector
      include agora.orchestrator
      description "Component breakdown van de HAI - UI Components, Audio Interface, WebSocket Client"
    }
    
    component agora.toolCatalog "ToolCatalogComponents" {
      include *
      include agora.orchestrator
      description "Component breakdown van de Tool Catalog database - Tool Registry, Tool Config"
    }
    
    component agora.userProfile "UserProfileComponents" {
      include *
      include agora.orchestrator
      description "Component breakdown van de User Profile database - Profile Data, Preferences, History"
    }
    
    styles {
      element "Person" {
        shape person
        background #08427b
        color #ffffff
      }
      element "Software System" {
        background #1168bd
        color #ffffff
      }
      element "Container" {
        background #438dd5
        color #ffffff
      }
      element "Frontend" {
        shape WebBrowser
        background #438dd5
        color #ffffff
      }
      element "Backend" {
        shape Hexagon
        background #438dd5
        color #ffffff
      }
      element "Database" {
        shape Cylinder
        background #438dd5
        color #ffffff
      }
      element "Observability" {
        shape RoundedBox
        background #438dd5
        color #ffffff
        fontSize 20
        stroke #ffffff
        strokeWidth 3
      }
      element "Component" {
        background #85bbf0
        color #000000
      }
      element "Infrastructure Node" {
        shape RoundedBox
      }
      relationship "Relationship" {
        routing Direct
        thickness 2
      }
    }
    
    theme default
  }
  
  configuration {
    scope softwaresystem
  }
}

