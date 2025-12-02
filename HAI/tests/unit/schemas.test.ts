import { describe, it, expect } from 'vitest';
import { 
  EventType,
  RunStartedEventSchema,
  RunFinishedEventSchema,
  RunErrorEventSchema,
  TextMessageStartEventSchema,
  TextMessageContentEventSchema,
  TextMessageEndEventSchema,
  ToolCallStartEventSchema,
  ToolCallArgsEventSchema,
  ToolCallEndEventSchema,
  ToolCallResultEventSchema,
  CustomEventSchema,
  StateSnapshotEventSchema,
  AGUIEventSchema,
  ToolApprovalRequestPayloadSchema,
  RunAgentInputSchema,
  isToolApprovalRequest,
  parseToolApprovalRequest,
  AGORA_TOOL_APPROVAL_REQUEST,
} from '@/types/schemas';

describe('AG-UI Protocol Schemas', () => {
  describe('Lifecycle Events', () => {
    it('validates RunStartedEvent', () => {
      const event = {
        type: EventType.RUN_STARTED,
        threadId: 'thread_123',
        runId: 'run_456',
        timestamp: Date.now(),
      };
      const result = RunStartedEventSchema.safeParse(event);
      expect(result.success).toBe(true);
    });

    it('validates RunFinishedEvent', () => {
      const event = {
        type: EventType.RUN_FINISHED,
        threadId: 'thread_123',
        runId: 'run_456',
        result: { success: true },
        timestamp: Date.now(),
      };
      const result = RunFinishedEventSchema.safeParse(event);
      expect(result.success).toBe(true);
    });

    it('validates RunErrorEvent', () => {
      const event = {
        type: EventType.RUN_ERROR,
        message: 'Something went wrong',
        code: 'ERR_001',
        timestamp: Date.now(),
      };
      const result = RunErrorEventSchema.safeParse(event);
      expect(result.success).toBe(true);
    });
  });

  describe('Text Message Events', () => {
    it('validates TextMessageStartEvent', () => {
      const event = {
        type: EventType.TEXT_MESSAGE_START,
        messageId: 'msg_123',
        role: 'assistant',
        timestamp: Date.now(),
      };
      const result = TextMessageStartEventSchema.safeParse(event);
      expect(result.success).toBe(true);
    });

    it('validates TextMessageContentEvent', () => {
      const event = {
        type: EventType.TEXT_MESSAGE_CONTENT,
        messageId: 'msg_123',
        delta: 'Hello, ',
        timestamp: Date.now(),
      };
      const result = TextMessageContentEventSchema.safeParse(event);
      expect(result.success).toBe(true);
    });

    it('validates TextMessageEndEvent', () => {
      const event = {
        type: EventType.TEXT_MESSAGE_END,
        messageId: 'msg_123',
        timestamp: Date.now(),
      };
      const result = TextMessageEndEventSchema.safeParse(event);
      expect(result.success).toBe(true);
    });

    it('validates all supported roles', () => {
      const roles = ['user', 'assistant', 'developer', 'system'];
      roles.forEach(role => {
        const event = {
          type: EventType.TEXT_MESSAGE_START,
          messageId: 'msg_123',
          role,
        };
        const result = TextMessageStartEventSchema.safeParse(event);
        expect(result.success).toBe(true);
      });
    });
  });

  describe('Tool Call Events', () => {
    it('validates ToolCallStartEvent', () => {
      const event = {
        type: EventType.TOOL_CALL_START,
        toolCallId: 'call_123',
        toolCallName: 'search_regulations',
        parentMessageId: 'msg_123',
        timestamp: Date.now(),
      };
      const result = ToolCallStartEventSchema.safeParse(event);
      expect(result.success).toBe(true);
    });

    it('validates ToolCallArgsEvent', () => {
      const event = {
        type: EventType.TOOL_CALL_ARGS,
        toolCallId: 'call_123',
        delta: '{"query": "voedselveiligheid"}',
        timestamp: Date.now(),
      };
      const result = ToolCallArgsEventSchema.safeParse(event);
      expect(result.success).toBe(true);
    });

    it('validates ToolCallEndEvent', () => {
      const event = {
        type: EventType.TOOL_CALL_END,
        toolCallId: 'call_123',
        timestamp: Date.now(),
      };
      const result = ToolCallEndEventSchema.safeParse(event);
      expect(result.success).toBe(true);
    });

    it('validates ToolCallResultEvent', () => {
      const event = {
        type: EventType.TOOL_CALL_RESULT,
        messageId: 'msg_456',
        toolCallId: 'call_123',
        content: 'Found 3 relevant regulations',
        role: 'tool',
        timestamp: Date.now(),
      };
      const result = ToolCallResultEventSchema.safeParse(event);
      expect(result.success).toBe(true);
    });
  });

  describe('Custom Events (AGORA Extensions)', () => {
    it('validates CustomEvent structure', () => {
      const event = {
        type: EventType.CUSTOM,
        name: 'agora:tool_approval_request',
        value: { approvalId: 'apr_123' },
        timestamp: Date.now(),
      };
      const result = CustomEventSchema.safeParse(event);
      expect(result.success).toBe(true);
    });

    it('validates tool approval request payload', () => {
      const payload = {
        toolName: 'generate_final_report',
        toolDescription: 'Generates an official inspection report PDF',
        parameters: { inspection_id: 'INS-2024-001' },
        reasoning: 'User requested to finalize the inspection report',
        riskLevel: 'high',
        approvalId: 'apr_123',
      };
      const result = ToolApprovalRequestPayloadSchema.safeParse(payload);
      expect(result.success).toBe(true);
    });

    it('validates all risk levels', () => {
      const levels = ['low', 'medium', 'high', 'critical'];
      levels.forEach(level => {
        const payload = {
          toolName: 'test_tool',
          toolDescription: 'Test tool',
          parameters: {},
          reasoning: 'Test',
          riskLevel: level,
          approvalId: 'apr_123',
        };
        const result = ToolApprovalRequestPayloadSchema.safeParse(payload);
        expect(result.success).toBe(true);
      });
    });

    it('rejects invalid risk level', () => {
      const payload = {
        toolName: 'test_tool',
        toolDescription: 'Test tool',
        parameters: {},
        reasoning: 'Test',
        riskLevel: 'invalid',
        approvalId: 'apr_123',
      };
      const result = ToolApprovalRequestPayloadSchema.safeParse(payload);
      expect(result.success).toBe(false);
    });
  });

  describe('State Events', () => {
    it('validates StateSnapshotEvent', () => {
      const event = {
        type: EventType.STATE_SNAPSHOT,
        snapshot: {
          currentAgent: 'regulation-agent',
          pendingApproval: null,
        },
        timestamp: Date.now(),
      };
      const result = StateSnapshotEventSchema.safeParse(event);
      expect(result.success).toBe(true);
    });
  });

  describe('AGUIEventSchema (discriminated union)', () => {
    it('discriminates event types correctly', () => {
      const events = [
        { type: EventType.RUN_STARTED, threadId: 'th_1', runId: 'run_1' },
        { type: EventType.TEXT_MESSAGE_START, messageId: 'msg_1', role: 'assistant' },
        { type: EventType.TOOL_CALL_START, toolCallId: 'tc_1', toolCallName: 'test' },
        { type: EventType.CUSTOM, name: 'test', value: {} },
      ];

      events.forEach(event => {
        const result = AGUIEventSchema.safeParse(event);
        expect(result.success).toBe(true);
      });
    });

    it('rejects invalid event types', () => {
      const event = {
        type: 'INVALID_EVENT',
        data: 'test',
      };
      const result = AGUIEventSchema.safeParse(event);
      expect(result.success).toBe(false);
    });
  });

  describe('Client Input Schemas', () => {
    it('validates RunAgentInput', () => {
      const input = {
        threadId: 'thread_123',
        runId: 'run_456',
        messages: [
          { role: 'user', content: 'Hello', id: 'msg_1' },
        ],
        context: { sessionId: 'sess_123' },
      };
      const result = RunAgentInputSchema.safeParse(input);
      expect(result.success).toBe(true);
    });

    it('validates all message roles', () => {
      const roles = ['user', 'assistant', 'system', 'tool', 'developer'];
      roles.forEach(role => {
        const input = {
          threadId: 'thread_123',
          messages: [{ role, content: 'Test' }],
        };
        const result = RunAgentInputSchema.safeParse(input);
        expect(result.success).toBe(true);
      });
    });
  });

  describe('Helper Functions', () => {
    it('isToolApprovalRequest identifies approval requests', () => {
      const event = {
        type: EventType.CUSTOM,
        name: AGORA_TOOL_APPROVAL_REQUEST,
        value: {},
      };
      expect(isToolApprovalRequest(event)).toBe(true);
    });

    it('parseToolApprovalRequest extracts payload', () => {
      const event = {
        type: EventType.CUSTOM,
        name: AGORA_TOOL_APPROVAL_REQUEST,
        value: {
          toolName: 'test_tool',
          toolDescription: 'Test',
          parameters: {},
          reasoning: 'Test reason',
          riskLevel: 'medium',
          approvalId: 'apr_123',
        },
      };
      const payload = parseToolApprovalRequest(event);
      expect(payload).not.toBeNull();
      expect(payload?.toolName).toBe('test_tool');
      expect(payload?.approvalId).toBe('apr_123');
    });
  });
});
