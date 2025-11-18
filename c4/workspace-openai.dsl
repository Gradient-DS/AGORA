workspace "AGORA v1.0 — Multi-Agent Systeem NVWA" {
  !identifiers hierarchical
  
  model {
    inspector = person "Inspecteur" "NVWA medewerker die AGORA gebruikt voor dagelijks werk"
    
    agora = softwareSystem "AGORA" "Multi-agent systeem voor ondersteuning van NVWA inspecteurs" {
      
      // Core containers
      hai = container "Human Agent Interface (HAI)" "React + Vite + Zustand" "React" {
        description "Gebruikersinterface voor interactie met AGORA via tekst en spraak"
        tags "Frontend"
        
        // HAI components
        chatComponents = component "Chat Components" "React componenten voor chat UI" "React" {
          description "Chat interface, message list, input en tool call visualisaties"
        }
        approvalComponents = component "Approval Components" "Human-in-the-loop approval UI" "React" {
          description "Approval queue en dialog voor tool call approvals"
        }
        stateManagement = component "State Management" "Zustand stores" "TypeScript" {
          description "Client-side state stores: messages, sessions, connections, approvals, agents, users"
        }
        websocketClient = component "WebSocket Client" "HAI Protocol WebSocket" "TypeScript" {
          description "Real-time HAI protocol communicatie met backend"
        }
        
        chatComponents -> stateManagement "Leest/schrijft state"
        approvalComponents -> stateManagement "Leest/schrijft state"
        stateManagement -> websocketClient "Stuurt berichten"
      }
      
      orchestrator = container "Orchestrator" "OpenAI Agents SDK + FastAPI" "Python" {
        description "Centrale orchestratie-engine met multi-agent systeem, MCP tool registry en moderatie"
        tags "Backend"
        
        // Orchestrator components
        group "OpenAI Agents SDK Core" {
          agentRunner = component "Agent Runner" "OpenAI Agents SDK Runner" "Python" {
            description "Beheert agent executie met streaming support, tool callbacks en session management via SQLite"
          }
          agentRegistry = component "Agent Registry" "Multi-agent configuratie" "Python" {
            description "Registry van alle agents: general, regulation, reporting en history agents met handoff support"
          }
          moderator = component "Moderator" "Input/output validation" "Python" {
            description "Valideert user input en assistant output op blocked patterns en sensitive content"
          }
          auditLogger = component "Audit Logger" "OpenTelemetry logging" "Python" {
            description "Audit logging van alle berichten en beslissingen via OpenTelemetry"
          }
          sessionStorage = component "Session Storage" "SQLite database" "Python" {
            description "Conversation history en agent state opslag via Agents SDK SQLiteSession"
          }
        }
        
        mcpToolRegistry = component "MCP Tool Registry" "Native MCP integration" "Python" {
          description "Agent SDK native MCP server connecties voor tools en resources"
        }
        haiProtocolHandler = component "HAI Protocol Handler" "WebSocket protocol handler" "Python" {
          description "Beheert HAI protocol communicatie: user messages, assistant chunks, tool calls, status updates"
        }
        
        haiProtocolHandler -> agentRunner "Stuurt requests naar"
        agentRunner -> agentRegistry "Haalt agents op"
        agentRunner -> sessionStorage "Beheert conversatie state"
        agentRegistry -> mcpToolRegistry "Configureert MCP tools per agent"
        agentRunner -> moderator "Valideert input/output"
        agentRunner -> auditLogger "Logt events"
      }
      
      visibility = container "Visibility" "Grafana + Prometheus + OpenTelemetry" "Observability Stack" {
        description "Monitoring, logging en observability van het gehele AGORA systeem"
        tags "Observability"
      }
      
      // Internal relationships
      hai -> orchestrator "HAI Protocol" "WebSocket/JSON"
      orchestrator -> visibility "Traces & decisions" "OpenTelemetry"
      
      // Component-level external relationships
      // HAI components
      agora.hai.websocketClient -> orchestrator "Communiceert met" "WebSocket"
      agora.hai.websocketClient -> agora.orchestrator.haiProtocolHandler "Stuurt requests naar" "WebSocket"
      
      // Orchestrator components to internal containers
      agora.orchestrator.auditLogger -> agora.visibility "Stuurt logs" "OpenTelemetry"
    }
    
    // External systems
    externalServices = softwareSystem "External Services" "Externe MCP servers (Rapportage, ARIA-A Scanner, E-nummer Database, etc.)" {
      description "Collectie van externe services die tools en resources via MCP protocol aanbieden"
    }
    
    // Relationships
    inspector -> agora "Gebruikt" "Tekst/Spraak/Video"
    inspector -> agora.hai "Interacteert met" "HTTPS/WebSocket"
    inspector -> agora.hai.chatComponents "Gebruikt chat interface" "HTTPS"
    
    agora -> externalServices "Communiceert met services" "MCP Protocol"
    agora.orchestrator -> externalServices "Roept aan via MCP" "MCP Protocol"
    agora.orchestrator.mcpToolRegistry -> externalServices "Roept tools aan" "MCP"
  }
  
  views {
    systemContext agora "SystemContext" {
      include *
      autolayout lr 300 300
      description "System context diagram van AGORA v1.0 - Inspecteur gebruikt AGORA om met externe agents te communiceren"
    }
    
    container agora "Containers" {
      include inspector
      include agora.hai
      include agora.orchestrator
      include agora.visibility
      include externalServices
      autolayout tb 300 300
      description "Container diagram van AGORA v1.0 - HAI, Orchestrator, Visibility en externe MCP services"
    }
    
    component agora.orchestrator "OrchestratorComponents" {
      include *
      include agora.hai
      include agora.visibility
      include externalServices
      autolayout tb 300 300
      description "Component breakdown van de Orchestrator - Agent Runner, Agent Registry, MCP Tool Registry, Moderator, Audit Logger, HAI Protocol Handler, Session Storage"
    }
    
    component agora.hai "HAIComponents" {
      include *
      include inspector
      include agora.orchestrator
      autolayout tb 300 300
      description "Component breakdown van de HAI - Chat Components, Approval Components, State Management, WebSocket Client"
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

