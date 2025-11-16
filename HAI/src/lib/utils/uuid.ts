export function generateUUID(): string {
  return crypto.randomUUID();
}

export function generateSessionId(): string {
  return `session_${generateUUID()}`;
}

export function generateMessageId(): string {
  return `msg_${generateUUID()}`;
}

export function generateApprovalId(): string {
  return `approval_${generateUUID()}`;
}

