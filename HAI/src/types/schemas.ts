import { z } from 'zod';

export const UserMessageSchema = z.object({
  type: z.literal('user_message'),
  content: z.string(),
  session_id: z.string(),
  metadata: z.record(z.unknown()).default({}),
});

export const AssistantMessageSchema = z.object({
  type: z.literal('assistant_message'),
  content: z.string(),
  session_id: z.string().nullable(),
  agent_id: z.string().nullable(),
  metadata: z.record(z.unknown()).default({}),
});

export const AssistantMessageChunkSchema = z.object({
  type: z.literal('assistant_message_chunk'),
  content: z.string(),
  session_id: z.string(),
  agent_id: z.string().nullable().optional(),
  message_id: z.string(),
  is_final: z.boolean().default(false),
});

export const ToolApprovalRequestSchema = z.object({
  type: z.literal('tool_approval_request'),
  tool_name: z.string(),
  tool_description: z.string(),
  parameters: z.record(z.unknown()),
  reasoning: z.string(),
  risk_level: z.enum(['low', 'medium', 'high', 'critical']),
  session_id: z.string(),
  approval_id: z.string(),
});

export const ToolApprovalResponseSchema = z.object({
  type: z.literal('tool_approval_response'),
  approval_id: z.string(),
  approved: z.boolean(),
  feedback: z.string().nullable().optional(),
});

export const ErrorMessageSchema = z.object({
  type: z.literal('error'),
  error_code: z.string(),
  message: z.string(),
  details: z.record(z.unknown()).default({}),
});

export const StatusMessageSchema = z.object({
  type: z.literal('status'),
  status: z.enum(['thinking', 'routing', 'executing_tools', 'completed']),
  message: z.string().nullable().optional(),
  session_id: z.string().nullable().optional(),
});

export const ToolCallMessageSchema = z.object({
  type: z.literal('tool_call'),
  tool_name: z.string(),
  parameters: z.record(z.unknown()),
  session_id: z.string(),
  status: z.enum(['started', 'completed', 'failed']),
  result: z.string().nullable().optional(),
});

export const HAIMessageSchema = z.discriminatedUnion('type', [
  UserMessageSchema,
  AssistantMessageSchema,
  AssistantMessageChunkSchema,
  ToolApprovalRequestSchema,
  ToolApprovalResponseSchema,
  ErrorMessageSchema,
  StatusMessageSchema,
  ToolCallMessageSchema,
]);

export type UserMessage = z.infer<typeof UserMessageSchema>;
export type AssistantMessage = z.infer<typeof AssistantMessageSchema>;
export type AssistantMessageChunk = z.infer<typeof AssistantMessageChunkSchema>;
export type ToolApprovalRequest = z.infer<typeof ToolApprovalRequestSchema>;
export type ToolApprovalResponse = z.infer<typeof ToolApprovalResponseSchema>;
export type ErrorMessage = z.infer<typeof ErrorMessageSchema>;
export type StatusMessage = z.infer<typeof StatusMessageSchema>;
export type ToolCallMessage = z.infer<typeof ToolCallMessageSchema>;
export type HAIMessage = z.infer<typeof HAIMessageSchema>;

export type RiskLevel = 'low' | 'medium' | 'high' | 'critical';
export type ProcessingStatus = 'thinking' | 'routing' | 'executing_tools' | 'completed';
export type ConnectionStatus = 'disconnected' | 'connecting' | 'connected' | 'reconnecting' | 'error';

