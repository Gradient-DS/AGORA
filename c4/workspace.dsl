workspace "AGORA v1.0 — Multi-Agent Platform for NVWA" {
  !identifiers hierarchical
  
  model {
    # =========================================================================
    # ACTORS
    # =========================================================================
    inspector = person "NVWA Inspecteur" "Food safety inspector using AGORA for daily inspection work"
    
    # =========================================================================
    # AGORA SYSTEM
    # =========================================================================
    agora = softwareSystem "AGORA" "Multi-agent compliance platform for NVWA inspectors" {
      
      # =======================================================================
      # HAI FRONTEND [Shared]
      # =======================================================================
      hai = container "Human Agent Interface (HAI)" "React + Vite + Zustand + TailwindCSS" "React SPA" {
        description "[Shared] Web-based user interface for inspector interactions via text"
        tags "Frontend" "Shared"
        
        chatComponents = component "[Shared] Chat Components" "React" {
          description "ChatInterface, ChatMessageList, ChatInput, ChatMessage, ToolCallCard, LoadingIndicator"
          tags "Shared"
        }
        approvalDialog = component "[Shared] Approval Dialog" "React" {
          description "ApprovalDialog for human-in-the-loop tool approval workflow"
          tags "Shared"
        }
        debugPanel = component "[Shared] Debug Panel" "React" {
          description "Tool call visualization and debugging interface"
          tags "Shared"
        }
        stateManagement = component "[Shared] State Management" "Zustand" {
          description "Client stores: useMessageStore, useSessionStore, useConnectionStore, useApprovalStore, useAgentStore, useToolCallStore"
          tags "Shared"
        }
        websocketClient = component "[Shared] WebSocket Client" "TypeScript" {
          description "HAI Protocol WebSocket client for real-time bidirectional communication"
          tags "Shared"
        }
        voiceInterface = component "[Shared] Voice Interface" "React + Whisper + ElevenLabs" {
          description "[NOT IMPLEMENTED] Speech-to-text and text-to-speech interface"
          tags "NotImplemented" "Shared"
        }
        
        chatComponents -> stateManagement "reads/writes" "Zustand selectors"
        approvalDialog -> stateManagement "reads/writes" "Zustand selectors"
        debugPanel -> stateManagement "reads" "Zustand selectors"
        stateManagement -> websocketClient "dispatches messages" "TypeScript"
      }
      
      # =======================================================================
      # ORCHESTRATOR - Unified (for C2 and external appearances)
      # =======================================================================
      orchestrator = container "Orchestrator [OpenAI/OpenSource]" "FastAPI + SQLite + OpenAI SDK or LangGraph" "Python" {
        description "Central orchestration for multi-agent coordination. See C3 diagrams for implementation-specific details."
        tags "Backend"
      }
      
      # =======================================================================
      # ORCHESTRATOR - OpenAI Agents SDK (for C3 detail view)
      # =======================================================================
      orchestratorOpenAI = container "Orchestrator [OpenAI]" "FastAPI + SQLite + OpenAI Agents SDK" "Python" {
        description "Central orchestration using OpenAI Agents SDK with native handoffs and MCP support."
        tags "Backend" "OpenAI"
        
        group "API Layer [Shared]" {
          oaiFastApiServer = component "[Shared] FastAPI Server" "FastAPI + Uvicorn" {
            description "HTTP server with WebSocket support at /ws endpoint"
            tags "Shared"
          }
          oaiHaiProtocolHandler = component "[Shared] HAI Protocol Handler" "Python" {
            description "Processes HAI Protocol messages: user_message, assistant_message_chunk, tool_call, tool_approval_request/response, status, error"
            tags "Shared"
          }
          oaiRestEndpoints = component "[Shared] REST Endpoints" "FastAPI" {
            description "/health, /agents, /sessions/{id}/history endpoints"
            tags "Shared"
          }
        }
        
        group "Pipelines Layer [Shared]" {
          oaiOrchestratorPipeline = component "[Shared] Orchestrator Pipeline" "Python" {
            description "Main message processing with approval flow management using stream callbacks"
            tags "Shared"
          }
          oaiModerator = component "[Shared] Moderator" "Python" {
            description "Input validation, output filtering, blocked patterns detection"
            tags "Shared"
          }
        }
        
        group "Core Layer [OpenAI]" {
          oaiAgentDefinitions = component "[OpenAI] Agent Definitions" "agents.Agent" {
            description "SDK Agent instances with instructions and handoff configuration"
            tags "OpenAI"
          }
          oaiAgentExecutor = component "[OpenAI] Agent Executor" "agents.Runner" {
            description "Runner.run_streamed() for streaming responses with tool callbacks"
            tags "OpenAI"
          }
          oaiHandoffLogic = component "[OpenAI] Handoff Logic" "SDK built-in" {
            description "Built-in SDK handoffs via agent.handoffs list - automatic context transfer"
            tags "OpenAI"
          }
          oaiApprovalLogic = component "[Shared] Approval Logic" "Python" {
            description "Human-in-loop rules for high-risk tools"
            tags "Shared"
          }
          oaiSessionPersistence = component "[OpenAI] Session Persistence" "agents.SQLiteSession" {
            description "SDK SQLiteSession for conversation history (sessions.db)"
            tags "OpenAI"
          }
        }
        
        group "Adapters Layer" {
          oaiMcpAdapter = component "[OpenAI] MCP Adapter" "MCPServerStreamableHttp" {
            description "Native OpenAI SDK MCP integration with per-agent tool scoping via AGENT_MCP_MAPPING"
            tags "OpenAI"
          }
          oaiAuditLogger = component "[Shared] Audit Logger" "OpenTelemetry" {
            description "OpenTelemetry-based audit logging of messages and decisions"
            tags "Shared"
          }
        }
        
        oaiRateLimiter = component "[Shared] Rate Limiter" "Python" {
          description "[NOT IMPLEMENTED] API rate limiting per user/IP"
          tags "NotImplemented" "Shared"
        }
        oaiCircuitBreaker = component "[Shared] Circuit Breaker" "Python" {
          description "[NOT IMPLEMENTED] Circuit breaker pattern for MCP server calls"
          tags "NotImplemented" "Shared"
        }
        
        oaiFastApiServer -> oaiHaiProtocolHandler "routes WebSocket" "WebSocket"
        oaiFastApiServer -> oaiRestEndpoints "routes HTTP" "HTTP/REST"
        oaiHaiProtocolHandler -> oaiOrchestratorPipeline "processes messages"
        oaiOrchestratorPipeline -> oaiAgentExecutor "runs agents"
        oaiOrchestratorPipeline -> oaiModerator "validates I/O"
        oaiOrchestratorPipeline -> oaiApprovalLogic "checks approval"
        oaiAgentExecutor -> oaiAgentDefinitions "gets agents"
        oaiAgentExecutor -> oaiHandoffLogic "handles handoffs"
        oaiAgentExecutor -> oaiSessionPersistence "persists state" "SQLite"
        oaiAgentDefinitions -> oaiMcpAdapter "configures tools" "MCP config"
        oaiOrchestratorPipeline -> oaiAuditLogger "logs events" "OpenTelemetry"
      }
      
      # =======================================================================
      # ORCHESTRATOR - LangGraph (Open Source) (for C3 detail view)
      # =======================================================================
      orchestratorLangGraph = container "Orchestrator [OpenSource]" "LangGraph + FastAPI + SQLite" "Python" {
        description "Central orchestration using LangGraph StateGraph (LLM provider-agnostic)."
        tags "Backend" "OpenSource"
        
        group "API Layer [Shared]" {
          lgFastApiServer = component "[Shared] FastAPI Server" "FastAPI + Uvicorn" {
            description "HTTP server with WebSocket support at /ws endpoint"
            tags "Shared"
          }
          lgHaiProtocolHandler = component "[Shared] HAI Protocol Handler" "Python" {
            description "Processes HAI Protocol messages: user_message, assistant_message_chunk, tool_call, tool_approval_request/response, status, error"
            tags "Shared"
          }
          lgRestEndpoints = component "[Shared] REST Endpoints" "FastAPI" {
            description "/health, /agents, /sessions/{id}/history endpoints"
            tags "Shared"
          }
        }
        
        group "Pipelines Layer [Shared]" {
          lgOrchestratorPipeline = component "[Shared] Orchestrator Pipeline" "Python" {
            description "Main message processing with approval flow management using astream_events"
            tags "Shared"
          }
          lgModerator = component "[Shared] Moderator" "Python" {
            description "Input validation, output filtering, blocked patterns detection"
            tags "Shared"
          }
        }
        
        group "Core Layer [OpenSource]" {
          lgAgentDefinitions = component "[OpenSource] Agent Definitions" "Python async functions" {
            description "Async functions (general_agent, regulation_agent, etc.) invoking ChatOpenAI with bound tools"
            tags "OpenSource"
          }
          lgAgentExecutor = component "[OpenSource] Agent Executor" "langgraph.StateGraph" {
            description "StateGraph with AgentState TypedDict, astream_events() for streaming"
            tags "OpenSource"
          }
          lgToolExecutor = component "[OpenSource] Tool Executor" "langgraph.prebuilt.ToolNode" {
            description "Prebuilt ToolNode handles all tool calls including handoffs"
            tags "OpenSource"
          }
          lgHandoffLogic = component "[OpenSource] Handoff Logic" "Python" {
            description "Explicit transfer_to_* tools that must go through ToolNode first"
            tags "OpenSource"
          }
          lgRoutingLogic = component "[OpenSource] Routing Logic" "Python" {
            description "route_from_agent() → 'tools'|'end', route_after_tools() → detects handoff → target agent"
            tags "OpenSource"
          }
          lgApprovalLogic = component "[Shared] Approval Logic" "Python" {
            description "Human-in-loop rules for high-risk tools"
            tags "Shared"
          }
          lgSessionPersistence = component "[OpenSource] Session Persistence" "AsyncSqliteSaver" {
            description "LangGraph checkpointer for conversation state (sessions.db)"
            tags "OpenSource"
          }
        }
        
        group "Adapters Layer" {
          lgMcpAdapter = component "[OpenSource] MCP Adapter" "MultiServerMCPClient" {
            description "langchain-mcp-adapters for MCP server connections with per-agent tool scoping"
            tags "OpenSource"
          }
          lgAuditLogger = component "[Shared] Audit Logger" "OpenTelemetry" {
            description "OpenTelemetry-based audit logging of messages and decisions"
            tags "Shared"
          }
        }
        
        lgRateLimiter = component "[Shared] Rate Limiter" "Python" {
          description "[NOT IMPLEMENTED] API rate limiting per user/IP"
          tags "NotImplemented" "Shared"
        }
        lgCircuitBreaker = component "[Shared] Circuit Breaker" "Python" {
          description "[NOT IMPLEMENTED] Circuit breaker pattern for MCP server calls"
          tags "NotImplemented" "Shared"
        }
        
        lgFastApiServer -> lgHaiProtocolHandler "routes WebSocket" "WebSocket"
        lgFastApiServer -> lgRestEndpoints "routes HTTP" "HTTP/REST"
        lgHaiProtocolHandler -> lgOrchestratorPipeline "processes messages"
        lgOrchestratorPipeline -> lgAgentExecutor "invokes graph"
        lgOrchestratorPipeline -> lgModerator "validates I/O"
        lgOrchestratorPipeline -> lgApprovalLogic "checks approval"
        lgAgentExecutor -> lgToolExecutor "executes tools"
        lgAgentExecutor -> lgRoutingLogic "determines next"
        lgToolExecutor -> lgHandoffLogic "executes handoffs"
        lgRoutingLogic -> lgAgentDefinitions "routes to agent"
        lgAgentExecutor -> lgSessionPersistence "persists state" "SQLite"
        lgAgentDefinitions -> lgMcpAdapter "binds tools"
        lgOrchestratorPipeline -> lgAuditLogger "logs events" "OpenTelemetry"
      }
      
      # =======================================================================
      # MCP AGENT SERVERS [Shared]
      # =======================================================================
      mcpServers = container "MCP Agent Servers" "FastMCP + Python" "Docker" {
        description "[Shared] Domain-specific agent capabilities exposed via MCP Protocol. Extensible by adding new MCP servers."
        tags "Backend" "Extensible" "Shared"
        
        regulationServer = component "[Shared] Regulation Agent" "FastMCP :5002" {
          description "Tools: search_regulations, get_regulation_context, lookup_regulation_articles, analyze_document"
          tags "Shared"
        }
        reportingServer = component "[Shared] Reporting Agent" "FastMCP :5003" {
          description "Tools: start_inspection_report, extract_inspection_data, verify_inspection_data, generate_final_report"
          tags "Shared"
        }
        historyServer = component "[Shared] History Agent" "FastMCP :5005" {
          description "Tools: check_company_exists, get_inspection_history, get_company_violations, check_repeat_violation"
          tags "Shared"
        }
      }
      
      # =======================================================================
      # MISSING CONTAINERS [Shared] - Production Gap Analysis
      # =======================================================================
      userProfile = container "User Profile" "PostgreSQL" "Database" {
        description "[Shared] [NOT IMPLEMENTED] User profiles, preferences, roles (RBAC)"
        tags "Database" "NotImplemented" "Shared"
      }
      
      memory = container "Memory Service" "Vector DB + PostgreSQL" "Service" {
        description "[Shared] [NOT IMPLEMENTED] Long-term memory, cross-session context"
        tags "Backend" "NotImplemented" "Shared"
      }
      
      visibility = container "Visibility Stack" "Grafana + Prometheus + Jaeger" "Observability" {
        description "[Shared] [NOT IMPLEMENTED] Monitoring, logging, tracing dashboards"
        tags "Observability" "NotImplemented" "Shared"
      }
      
      evalService = container "Evaluation Service" "Langfuse" "Observability" {
        description "[Shared] [NOT IMPLEMENTED] LLM tracing, quality evaluations, cost tracking"
        tags "Observability" "NotImplemented" "Shared"
      }
      
      authService = container "Auth Service" "Auth0/Keycloak" "Security" {
        description "[Shared] [NOT IMPLEMENTED] OAuth2/OIDC authentication, RBAC"
        tags "Security" "NotImplemented" "Shared"
      }
      
      # =======================================================================
      # INTERNAL CONTAINER RELATIONSHIPS (Unified orchestrator for C2/external)
      # =======================================================================
      # HAI connects to unified orchestrator
      hai -> orchestrator "HAI Protocol" "WebSocket/JSON :8001"
      
      # Unified orchestrator connects to shared MCP servers
      orchestrator -> mcpServers "MCP Protocol" "HTTP/SSE Streamable"
      
      # Observability connections (not implemented)
      orchestrator -> visibility "[NOT CONNECTED]" "OpenTelemetry OTLP"
      orchestrator -> evalService "[NOT CONNECTED]" "Langfuse SDK"
      
      # =======================================================================
      # COMPONENT-LEVEL RELATIONSHIPS (for C3 views)
      # =======================================================================
      # HAI to unified orchestrator (for C3 HAI view)
      agora.hai.websocketClient -> agora.orchestrator "HAI Protocol" "WebSocket"
      
      # OpenAI Orchestrator MCP connections (for C3 OpenAI view)
      agora.orchestratorOpenAI.oaiMcpAdapter -> agora.mcpServers.regulationServer "MCP" "HTTP POST /mcp"
      agora.orchestratorOpenAI.oaiMcpAdapter -> agora.mcpServers.reportingServer "MCP" "HTTP POST /mcp"
      agora.orchestratorOpenAI.oaiMcpAdapter -> agora.mcpServers.historyServer "MCP" "HTTP POST /mcp"
      
      # LangGraph Orchestrator MCP connections (for C3 OpenSource view)
      agora.orchestratorLangGraph.lgMcpAdapter -> agora.mcpServers.regulationServer "MCP" "HTTP POST /mcp"
      agora.orchestratorLangGraph.lgMcpAdapter -> agora.mcpServers.reportingServer "MCP" "HTTP POST /mcp"
      agora.orchestratorLangGraph.lgMcpAdapter -> agora.mcpServers.historyServer "MCP" "HTTP POST /mcp"
      
      # HAI WebSocket connections (for C3 orchestrator detail views)
      agora.hai.websocketClient -> agora.orchestratorOpenAI.oaiFastApiServer "HAI Protocol" "WebSocket"
      agora.hai.websocketClient -> agora.orchestratorLangGraph.lgFastApiServer "HAI Protocol" "WebSocket"
      
      # Unified Orchestrator to MCP Agent connections (for C3 MCP view)
      agora.orchestrator -> agora.mcpServers.regulationServer "MCP" "HTTP POST /mcp"
      agora.orchestrator -> agora.mcpServers.reportingServer "MCP" "HTTP POST /mcp"
      agora.orchestrator -> agora.mcpServers.historyServer "MCP" "HTTP POST /mcp"
    }
    
    # =========================================================================
    # MCP AGENT ECOSYSTEM (C1 Level)
    # =========================================================================
    mcpEcosystem = softwareSystem "MCP Agent Ecosystem" "[Shared] Extensible domain agents via Model Context Protocol. Add new capabilities by deploying MCP servers." {
      tags "Extensible"
    }
    
    # =========================================================================
    # C1 RELATIONSHIPS
    # =========================================================================
    inspector -> agora "uses for inspections" "HTTPS/WebSocket"
    agora -> mcpEcosystem "orchestrates agents" "MCP Protocol"
  }
  
  views {
    # =========================================================================
    # C1: SYSTEM CONTEXT
    # =========================================================================
    systemContext agora "C1_SystemContext" {
      include inspector
      include agora
      include mcpEcosystem
      autolayout lr 400 200
      description "System Context (C1): Inspector → AGORA → MCP Agent Ecosystem"
    }
    
    # =========================================================================
    # C2: CONTAINER DIAGRAM (Unified orchestrator)
    # =========================================================================
    container agora "C2_Containers" {
      include agora.hai
      include agora.orchestrator
      include agora.mcpServers
      include agora.userProfile
      include agora.memory
      include agora.visibility
      include agora.evalService
      include agora.authService
      autolayout tb 350 200
      description "Container Diagram (C2): HAI → Orchestrator [OpenAI/OpenSource] → MCP Agent Servers (+ future services)"
    }
    
    # =========================================================================
    # C3: HAI COMPONENTS [Shared]
    # =========================================================================
    component agora.hai "C3_HAI_Components" {
      include *
      include agora.orchestrator
      exclude agora.orchestratorOpenAI
      exclude agora.orchestratorLangGraph
      autolayout tb 300 150
      description "Component Diagram (C3): HAI Frontend - all [Shared] between backends"
    }
    
    # =========================================================================
    # C3: ORCHESTRATOR [OpenAI] - Detailed implementation view
    # =========================================================================
    component agora.orchestratorOpenAI "C3_Orchestrator_OpenAI" {
      include *
      include agora.hai
      include agora.mcpServers
      autolayout tb 250 150
      description "Component Diagram (C3): Orchestrator [OpenAI] - SDK Agent/Runner/Handoffs"
    }
    
    # =========================================================================
    # C3: ORCHESTRATOR [OpenSource] - Detailed implementation view
    # =========================================================================
    component agora.orchestratorLangGraph "C3_Orchestrator_OpenSource" {
      include *
      include agora.hai
      include agora.mcpServers
      autolayout tb 250 150
      description "Component Diagram (C3): Orchestrator [OpenSource] - StateGraph/ToolNode/Routing"
    }
    
    # =========================================================================
    # C3: MCP AGENT SERVERS [Shared]
    # =========================================================================
    component agora.mcpServers "C3_MCP_Components" {
      include *
      include agora.orchestrator
      exclude agora.orchestratorOpenAI
      exclude agora.orchestratorLangGraph
      autolayout lr 300 150
      description "Component Diagram (C3): MCP Agent Servers - all [Shared] between backends"
    }
    
    # =========================================================================
    # STYLES
    # =========================================================================
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
      element "External" {
        background #999999
        color #ffffff
      }
      element "Extensible" {
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
        border dashed
      }
      element "Security" {
        shape RoundedBox
        background #438dd5
        color #ffffff
        border dashed
      }
      element "Component" {
        background #85bbf0
        color #000000
      }
      element "Shared" {
        background #85bbf0
        color #000000
      }
      element "OpenAI" {
        background #74aa9c
        color #000000
      }
      element "OpenSource" {
        background #ff9966
        color #000000
      }
      element "NotImplemented" {
        background #ffcccc
        color #990000
        border dashed
        opacity 70
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

