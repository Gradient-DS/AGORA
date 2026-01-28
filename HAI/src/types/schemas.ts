/**
 * AG-UI Protocol event schemas for AGORA HAI.
 *
 * These Zod schemas match the official AG-UI Protocol event types used for
 * communication between the HAI frontend and the LangGraph backend.
 *
 * Reference: https://github.com/ag-ui-protocol/ag-ui
 */

import { z } from 'zod';

export const EventType = {
  RUN_STARTED: 'RUN_STARTED',
  RUN_FINISHED: 'RUN_FINISHED',
  RUN_ERROR: 'RUN_ERROR',
  STEP_STARTED: 'STEP_STARTED',
  STEP_FINISHED: 'STEP_FINISHED',
  TEXT_MESSAGE_START: 'TEXT_MESSAGE_START',
  TEXT_MESSAGE_CONTENT: 'TEXT_MESSAGE_CONTENT',
  TEXT_MESSAGE_END: 'TEXT_MESSAGE_END',
  TOOL_CALL_START: 'TOOL_CALL_START',
  TOOL_CALL_ARGS: 'TOOL_CALL_ARGS',
  TOOL_CALL_END: 'TOOL_CALL_END',
  TOOL_CALL_RESULT: 'TOOL_CALL_RESULT',
  STATE_SNAPSHOT: 'STATE_SNAPSHOT',
  STATE_DELTA: 'STATE_DELTA',
  MESSAGES_SNAPSHOT: 'MESSAGES_SNAPSHOT',
  CUSTOM: 'CUSTOM',
  RAW: 'RAW',
} as const;

export type EventTypeValue = (typeof EventType)[keyof typeof EventType];

// Lifecycle Events
export const RunStartedEventSchema = z.object({
  type: z.literal(EventType.RUN_STARTED),
  threadId: z.string(),
  runId: z.string(),
  parentRunId: z.string().nullable().optional(),
  timestamp: z.number().nullable().optional(),
});

export const RunFinishedEventSchema = z.object({
  type: z.literal(EventType.RUN_FINISHED),
  threadId: z.string(),
  runId: z.string(),
  result: z.unknown().nullable().optional(),
  timestamp: z.number().nullable().optional(),
});

export const RunErrorEventSchema = z.object({
  type: z.literal(EventType.RUN_ERROR),
  message: z.string(),
  code: z.string().nullable().optional(),
  timestamp: z.number().nullable().optional(),
});

export const StepStartedEventSchema = z.object({
  type: z.literal(EventType.STEP_STARTED),
  stepName: z.string(),
  timestamp: z.number().nullable().optional(),
});

export const StepFinishedEventSchema = z.object({
  type: z.literal(EventType.STEP_FINISHED),
  stepName: z.string(),
  timestamp: z.number().nullable().optional(),
});

// Text Message Events
export const TextMessageStartEventSchema = z.object({
  type: z.literal(EventType.TEXT_MESSAGE_START),
  messageId: z.string(),
  role: z.enum(['user', 'assistant', 'developer', 'system']),
  timestamp: z.number().nullable().optional(),
});

export const TextMessageContentEventSchema = z.object({
  type: z.literal(EventType.TEXT_MESSAGE_CONTENT),
  messageId: z.string(),
  delta: z.string(),
  timestamp: z.number().nullable().optional(),
});

export const TextMessageEndEventSchema = z.object({
  type: z.literal(EventType.TEXT_MESSAGE_END),
  messageId: z.string(),
  timestamp: z.number().nullable().optional(),
});

// Tool Call Events
export const ToolCallStartEventSchema = z.object({
  type: z.literal(EventType.TOOL_CALL_START),
  toolCallId: z.string(),
  toolCallName: z.string(),
  toolDescription: z.string().nullable().optional(),
  toolDisplayName: z.string().nullable().optional(),
  parentMessageId: z.string().nullable().optional(),
  timestamp: z.number().nullable().optional(),
});

export const ToolCallArgsEventSchema = z.object({
  type: z.literal(EventType.TOOL_CALL_ARGS),
  toolCallId: z.string(),
  delta: z.string(),
  timestamp: z.number().nullable().optional(),
});

export const ToolCallEndEventSchema = z.object({
  type: z.literal(EventType.TOOL_CALL_END),
  toolCallId: z.string(),
  timestamp: z.number().nullable().optional(),
});

export const ToolCallResultEventSchema = z.object({
  type: z.literal(EventType.TOOL_CALL_RESULT),
  messageId: z.string(),
  toolCallId: z.string(),
  content: z.string(),
  role: z.literal('tool').nullable().optional(),
  timestamp: z.number().nullable().optional(),
});

// State Events
export const StateSnapshotEventSchema = z.object({
  type: z.literal(EventType.STATE_SNAPSHOT),
  snapshot: z.record(z.unknown()),
  timestamp: z.number().nullable().optional(),
});

export const StateDeltaEventSchema = z.object({
  type: z.literal(EventType.STATE_DELTA),
  delta: z.array(z.record(z.unknown())),
  timestamp: z.number().nullable().optional(),
});

export const MessagesSnapshotEventSchema = z.object({
  type: z.literal(EventType.MESSAGES_SNAPSHOT),
  messages: z.array(z.record(z.unknown())),
  timestamp: z.number().nullable().optional(),
});

// Custom Events
export const CustomEventSchema = z.object({
  type: z.literal(EventType.CUSTOM),
  name: z.string(),
  value: z.record(z.unknown()),
  timestamp: z.number().nullable().optional(),
});

export const RawEventSchema = z.object({
  type: z.literal(EventType.RAW),
  event: z.unknown(),
  source: z.string().nullable().optional(),
  timestamp: z.number().nullable().optional(),
});

// AGORA-specific custom event payloads
export const ToolApprovalRequestPayloadSchema = z.object({
  toolName: z.string(),
  toolDescription: z.string(),
  parameters: z.record(z.unknown()),
  reasoning: z.string(),
  riskLevel: z.enum(['low', 'medium', 'high', 'critical']),
  approvalId: z.string(),
});

export const ToolApprovalResponsePayloadSchema = z.object({
  approvalId: z.string(),
  approved: z.boolean(),
  feedback: z.string().nullable().optional(),
});

export const ErrorPayloadSchema = z.object({
  errorCode: z.string(),
  message: z.string(),
  details: z.record(z.unknown()).nullable().optional(),
});

// Custom event names used by AGORA
export const AGORA_TOOL_APPROVAL_REQUEST = 'agora:tool_approval_request';
export const AGORA_TOOL_APPROVAL_RESPONSE = 'agora:tool_approval_response';
export const AGORA_ERROR = 'agora:error';

// Union of all AG-UI events
export const AGUIEventSchema = z.discriminatedUnion('type', [
  RunStartedEventSchema,
  RunFinishedEventSchema,
  RunErrorEventSchema,
  StepStartedEventSchema,
  StepFinishedEventSchema,
  TextMessageStartEventSchema,
  TextMessageContentEventSchema,
  TextMessageEndEventSchema,
  ToolCallStartEventSchema,
  ToolCallArgsEventSchema,
  ToolCallEndEventSchema,
  ToolCallResultEventSchema,
  StateSnapshotEventSchema,
  StateDeltaEventSchema,
  MessagesSnapshotEventSchema,
  CustomEventSchema,
  RawEventSchema,
]);

// Input types (client → server)
export const RunAgentInputSchema = z.object({
  threadId: z.string(),
  runId: z.string().optional(),
  userId: z.string().uuid(),
  messages: z.array(
    z.object({
      role: z.enum(['user', 'assistant', 'system', 'tool', 'developer']),
      content: z.string(),
      id: z.string().optional(),
      toolCallId: z.string().optional(),
    })
  ),
});

export const MessageSchema = z.object({
  role: z.enum(['user', 'assistant', 'system', 'tool', 'developer']),
  content: z.string(),
  id: z.string().optional(),
  toolCallId: z.string().optional(),
});

// Type exports
export type RunStartedEvent = z.infer<typeof RunStartedEventSchema>;
export type RunFinishedEvent = z.infer<typeof RunFinishedEventSchema>;
export type RunErrorEvent = z.infer<typeof RunErrorEventSchema>;
export type StepStartedEvent = z.infer<typeof StepStartedEventSchema>;
export type StepFinishedEvent = z.infer<typeof StepFinishedEventSchema>;
export type TextMessageStartEvent = z.infer<typeof TextMessageStartEventSchema>;
export type TextMessageContentEvent = z.infer<typeof TextMessageContentEventSchema>;
export type TextMessageEndEvent = z.infer<typeof TextMessageEndEventSchema>;
export type ToolCallStartEvent = z.infer<typeof ToolCallStartEventSchema>;
export type ToolCallArgsEvent = z.infer<typeof ToolCallArgsEventSchema>;
export type ToolCallEndEvent = z.infer<typeof ToolCallEndEventSchema>;
export type ToolCallResultEvent = z.infer<typeof ToolCallResultEventSchema>;
export type StateSnapshotEvent = z.infer<typeof StateSnapshotEventSchema>;
export type StateDeltaEvent = z.infer<typeof StateDeltaEventSchema>;
export type MessagesSnapshotEvent = z.infer<typeof MessagesSnapshotEventSchema>;
export type CustomEvent = z.infer<typeof CustomEventSchema>;
export type RawEvent = z.infer<typeof RawEventSchema>;
export type AGUIEvent = z.infer<typeof AGUIEventSchema>;

export type ToolApprovalRequestPayload = z.infer<typeof ToolApprovalRequestPayloadSchema>;
export type ToolApprovalResponsePayload = z.infer<typeof ToolApprovalResponsePayloadSchema>;
export type ErrorPayload = z.infer<typeof ErrorPayloadSchema>;

export type RunAgentInput = z.infer<typeof RunAgentInputSchema>;
export type Message = z.infer<typeof MessageSchema>;

// Utility types
export type RiskLevel = 'low' | 'medium' | 'high' | 'critical';
export type ConnectionStatus = 'disconnected' | 'connecting' | 'connected' | 'reconnecting' | 'error';

// Helper to check if a custom event is a tool approval request
export function isToolApprovalRequest(event: CustomEvent): boolean {
  return event.name === AGORA_TOOL_APPROVAL_REQUEST;
}

// Helper to check if a custom event is an error
export function isAgoraError(event: CustomEvent): boolean {
  return event.name === AGORA_ERROR;
}

// Helper to parse tool approval request from custom event
export function parseToolApprovalRequest(event: CustomEvent): ToolApprovalRequestPayload | null {
  if (!isToolApprovalRequest(event)) return null;
  const result = ToolApprovalRequestPayloadSchema.safeParse(event.value);
  return result.success ? result.data : null;
}

// Helper to parse error from custom event
export function parseAgoraError(event: CustomEvent): ErrorPayload | null {
  if (!isAgoraError(event)) return null;
  const result = ErrorPayloadSchema.safeParse(event.value);
  return result.success ? result.data : null;
}
