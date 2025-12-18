/**
 * User management types matching the OpenAPI spec.
 */

export interface UserPreferences {
  theme?: 'light' | 'dark' | 'system';
  notifications_enabled?: boolean;
  default_agent_id?: string;
  language?: string;
}

export interface UserProfile {
  id: string;
  email: string;
  name: string;
  preferences?: UserPreferences;
  createdAt: string;
  lastActivity: string;
}

export interface CreateUserRequest {
  email: string;
  name: string;
}

export interface UpdateUserRequest {
  name?: string;
  preferences?: UserPreferences;
}

export interface UserListResponse {
  success: boolean;
  users: UserProfile[];
  totalCount: number;
}

export interface UserResponse {
  success: boolean;
  user: UserProfile;
}

export interface DeleteUserResponse {
  success: boolean;
  message: string;
  deletedSessionsCount: number;
}
