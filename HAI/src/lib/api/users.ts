/**
 * User management API functions.
 */

import { env } from '@/lib/env';
import type {
  UserProfile,
  CreateUserRequest,
  UpdateUserRequest,
  UserPreferences,
  UserListResponse,
  UserResponse,
  DeleteUserResponse,
} from '@/types/user';

/**
 * Get the HTTP base URL from the WebSocket URL.
 * Converts ws://host:port/ws to http://host:port
 */
function getBaseUrl(): string {
  const wsUrl = env.VITE_WS_URL;
  return wsUrl
    .replace(/^ws:/, 'http:')
    .replace(/^wss:/, 'https:')
    .replace(/\/ws\/?$/, '');
}

/**
 * Fetch all users with pagination.
 */
export async function fetchUsers(
  limit: number = 50,
  offset: number = 0
): Promise<{ users: UserProfile[]; totalCount: number }> {
  const baseUrl = getBaseUrl();
  const params = new URLSearchParams({
    limit: limit.toString(),
    offset: offset.toString(),
  });

  const url = `${baseUrl}/users?${params}`;
  console.log('[users API] Fetching users:', url);
  const response = await fetch(url);

  if (!response.ok) {
    throw new Error(`Failed to fetch users: ${response.statusText}`);
  }

  const data: UserListResponse = await response.json();
  console.log('[users API] Response:', data);

  if (!data.success) {
    throw new Error('Failed to fetch users');
  }

  return {
    users: data.users,
    totalCount: data.totalCount,
  };
}

/**
 * Fetch a single user by ID.
 */
export async function fetchUser(userId: string): Promise<UserProfile> {
  const baseUrl = getBaseUrl();
  const response = await fetch(`${baseUrl}/users/${userId}`);

  if (!response.ok) {
    if (response.status === 404) {
      throw new Error('User not found');
    }
    throw new Error(`Failed to fetch user: ${response.statusText}`);
  }

  const data: UserResponse = await response.json();

  if (!data.success) {
    throw new Error('Failed to fetch user');
  }

  return data.user;
}

/**
 * Create a new user.
 */
export async function createUser(userData: CreateUserRequest): Promise<UserProfile> {
  const baseUrl = getBaseUrl();
  const response = await fetch(`${baseUrl}/users`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(userData),
  });

  if (!response.ok) {
    if (response.status === 409) {
      throw new Error('Email already exists');
    }
    if (response.status === 400) {
      throw new Error('Invalid input: email and name are required');
    }
    throw new Error(`Failed to create user: ${response.statusText}`);
  }

  const data: UserResponse = await response.json();

  if (!data.success) {
    throw new Error('Failed to create user');
  }

  return data.user;
}

/**
 * Update an existing user.
 */
export async function updateUser(
  userId: string,
  userData: UpdateUserRequest
): Promise<UserProfile> {
  const baseUrl = getBaseUrl();
  const response = await fetch(`${baseUrl}/users/${userId}`, {
    method: 'PUT',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(userData),
  });

  if (!response.ok) {
    if (response.status === 404) {
      throw new Error('User not found');
    }
    throw new Error(`Failed to update user: ${response.statusText}`);
  }

  const data: UserResponse = await response.json();

  if (!data.success) {
    throw new Error('Failed to update user');
  }

  return data.user;
}

/**
 * Delete a user and all their sessions.
 */
export async function deleteUser(userId: string): Promise<DeleteUserResponse> {
  const baseUrl = getBaseUrl();
  const response = await fetch(`${baseUrl}/users/${userId}`, {
    method: 'DELETE',
  });

  if (!response.ok) {
    if (response.status === 404) {
      throw new Error('User not found');
    }
    throw new Error(`Failed to delete user: ${response.statusText}`);
  }

  const data: DeleteUserResponse = await response.json();

  if (!data.success) {
    throw new Error('Failed to delete user');
  }

  return data;
}

/**
 * Get the current authenticated user.
 */
export async function fetchCurrentUser(): Promise<UserProfile> {
  const baseUrl = getBaseUrl();
  const response = await fetch(`${baseUrl}/users/me`);

  if (!response.ok) {
    if (response.status === 401) {
      throw new Error('Not authenticated');
    }
    throw new Error(`Failed to fetch current user: ${response.statusText}`);
  }

  const data: UserProfile = await response.json();
  return data;
}

/**
 * Fetch preferences for the current user.
 */
export async function fetchUserPreferences(
  userId: string
): Promise<UserPreferences> {
  const baseUrl = getBaseUrl();
  const response = await fetch(
    `${baseUrl}/users/me/preferences?user_id=${encodeURIComponent(userId)}`
  );

  if (!response.ok) {
    throw new Error(`Failed to fetch preferences: ${response.statusText}`);
  }

  const data: { success: boolean; preferences: UserPreferences } = await response.json();

  if (!data.success) {
    throw new Error('Failed to fetch preferences');
  }

  return data.preferences;
}

/**
 * Update preferences for the current user.
 */
export async function updateUserPreferences(
  userId: string,
  preferences: UserPreferences
): Promise<UserPreferences> {
  const baseUrl = getBaseUrl();
  const response = await fetch(
    `${baseUrl}/users/me/preferences?user_id=${encodeURIComponent(userId)}`,
    {
      method: 'PUT',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(preferences),
    }
  );

  if (!response.ok) {
    throw new Error(`Failed to update preferences: ${response.statusText}`);
  }

  const data: { success: boolean; preferences: UserPreferences } = await response.json();

  if (!data.success) {
    throw new Error('Failed to update preferences');
  }

  return data.preferences;
}
