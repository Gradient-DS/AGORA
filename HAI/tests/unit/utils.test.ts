import { describe, it, expect } from 'vitest';
import { generateUUID, generateSessionId, generateMessageId, generateApprovalId } from '@/lib/utils';

describe('UUID utilities', () => {
  it('generates valid UUIDs', () => {
    const uuid = generateUUID();
    expect(uuid).toBeTruthy();
    expect(typeof uuid).toBe('string');
    expect(uuid.length).toBeGreaterThan(0);
  });

  it('generates unique UUIDs', () => {
    const uuid1 = generateUUID();
    const uuid2 = generateUUID();
    expect(uuid1).not.toBe(uuid2);
  });

  it('generates session IDs with prefix', () => {
    const sessionId = generateSessionId();
    expect(sessionId).toMatch(/^session_/);
  });

  it('generates message IDs with prefix', () => {
    const messageId = generateMessageId();
    expect(messageId).toMatch(/^msg_/);
  });

  it('generates approval IDs with prefix', () => {
    const approvalId = generateApprovalId();
    expect(approvalId).toMatch(/^approval_/);
  });
});

