import { describe, it, expect } from 'vitest';
import { 
  UserMessageSchema, 
  AssistantMessageSchema, 
  ToolApprovalRequestSchema,
  StatusMessageSchema,
  HAIMessageSchema 
} from '@/types/schemas';

describe('HAI Protocol Schemas', () => {
  describe('UserMessageSchema', () => {
    it('validates valid user message', () => {
      const message = {
        type: 'user_message',
        content: 'Hello',
        session_id: 'session_123',
        metadata: {},
      };
      const result = UserMessageSchema.safeParse(message);
      expect(result.success).toBe(true);
    });

    it('rejects invalid message type', () => {
      const message = {
        type: 'invalid_type',
        content: 'Hello',
        session_id: 'session_123',
      };
      const result = UserMessageSchema.safeParse(message);
      expect(result.success).toBe(false);
    });

    it('requires content and session_id', () => {
      const message = {
        type: 'user_message',
      };
      const result = UserMessageSchema.safeParse(message);
      expect(result.success).toBe(false);
    });
  });

  describe('AssistantMessageSchema', () => {
    it('validates valid assistant message', () => {
      const message = {
        type: 'assistant_message',
        content: 'Hi there!',
        session_id: 'session_123',
        agent_id: 'spec_agent',
        metadata: {},
      };
      const result = AssistantMessageSchema.safeParse(message);
      expect(result.success).toBe(true);
    });

    it('allows null values for optional fields', () => {
      const message = {
        type: 'assistant_message',
        content: 'Hi there!',
        session_id: null,
        agent_id: null,
        metadata: {},
      };
      const result = AssistantMessageSchema.safeParse(message);
      expect(result.success).toBe(true);
    });
  });

  describe('ToolApprovalRequestSchema', () => {
    it('validates valid approval request', () => {
      const request = {
        type: 'tool_approval_request',
        tool_name: 'execute_query',
        tool_description: 'Execute a database query',
        parameters: { query: 'SELECT * FROM users' },
        reasoning: 'Need to fetch user data',
        risk_level: 'medium',
        session_id: 'session_123',
        approval_id: 'approval_456',
      };
      const result = ToolApprovalRequestSchema.safeParse(request);
      expect(result.success).toBe(true);
    });

    it('validates risk levels', () => {
      const levels = ['low', 'medium', 'high', 'critical'];
      levels.forEach(level => {
        const request = {
          type: 'tool_approval_request',
          tool_name: 'test',
          tool_description: 'test',
          parameters: {},
          reasoning: 'test',
          risk_level: level,
          session_id: 'session_123',
          approval_id: 'approval_456',
        };
        const result = ToolApprovalRequestSchema.safeParse(request);
        expect(result.success).toBe(true);
      });
    });

    it('rejects invalid risk level', () => {
      const request = {
        type: 'tool_approval_request',
        tool_name: 'test',
        tool_description: 'test',
        parameters: {},
        reasoning: 'test',
        risk_level: 'invalid',
        session_id: 'session_123',
        approval_id: 'approval_456',
      };
      const result = ToolApprovalRequestSchema.safeParse(request);
      expect(result.success).toBe(false);
    });
  });

  describe('StatusMessageSchema', () => {
    it('validates valid status message', () => {
      const message = {
        type: 'status',
        status: 'thinking',
        message: 'Processing your request',
        session_id: 'session_123',
      };
      const result = StatusMessageSchema.safeParse(message);
      expect(result.success).toBe(true);
    });

    it('validates all status types', () => {
      const statuses = ['thinking', 'routing', 'executing_tools', 'completed'];
      statuses.forEach(status => {
        const message = {
          type: 'status',
          status,
          session_id: 'session_123',
        };
        const result = StatusMessageSchema.safeParse(message);
        expect(result.success).toBe(true);
      });
    });
  });

  describe('HAIMessageSchema', () => {
    it('discriminates message types correctly', () => {
      const messages = [
        { type: 'user_message', content: 'Hi', session_id: '123', metadata: {} },
        { type: 'assistant_message', content: 'Hello', session_id: '123', agent_id: null, metadata: {} },
        { type: 'status', status: 'thinking', message: null, session_id: '123' },
      ];

      messages.forEach(message => {
        const result = HAIMessageSchema.safeParse(message);
        expect(result.success).toBe(true);
      });
    });
  });
});

