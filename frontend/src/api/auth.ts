import axios from 'axios'
import { apiClient, setAccessToken } from './client.ts'
import { AUTH_CONFIG } from '../config/auth.ts'
import type {
  User,
  LoginPayload,
  RegisterPayload,
  AuthResponse,
  ApiErrorDetail,
} from '../types/auth.ts'

/**
 * Standardize errors coming from Django REST Framework
 */
export function formatApiError(err: unknown): ApiErrorDetail {
  if (axios.isAxiosError(err)) {
    if (err.response) {
      const data = err.response.data
      const statusCode = err.response.status

      if (typeof data === 'string') {
        return { message: data, statusCode }
      }

      if (data && typeof data === 'object') {
        if (typeof data.detail === 'string') {
          return { message: data.detail, statusCode }
        }
        if (typeof data.message === 'string') {
          const fieldErrors: Record<string, string[]> = {}
          if (data.fields && typeof data.fields === 'object') {
            for (const [key, value] of Object.entries(data.fields)) {
              fieldErrors[key] = Array.isArray(value) ? value.map(String) : [String(value)]
            }
          }
          const details = Object.entries(fieldErrors).map(([key, values]) => `${key.replaceAll('_', ' ')}: ${values.join(' ')}`)
          return { message: [data.message, ...details].join(' '), fieldErrors, statusCode }
        }

        if (Array.isArray(data.non_field_errors) && data.non_field_errors.length > 0) {
          return { message: String(data.non_field_errors[0]), statusCode }
        }

        const fieldErrors: Record<string, string[]> = {}
        const errorMessages: string[] = []

        for (const [key, value] of Object.entries(data)) {
          if (Array.isArray(value)) {
            fieldErrors[key] = value.map(String)
            errorMessages.push(`${key}: ${value[0]}`)
          } else if (typeof value === 'string') {
            fieldErrors[key] = [value]
            errorMessages.push(value)
          }
        }

        if (errorMessages.length > 0) {
          return {
            message: errorMessages[0],
            fieldErrors,
            statusCode,
          }
        }
      }

      if (statusCode === 401) {
        return { message: 'Invalid credentials. Please verify your email and password.', statusCode }
      }
      if (statusCode === 403) {
        return { message: 'Access forbidden. Please check your account permissions.', statusCode }
      }
      if (statusCode >= 500) {
        return { message: 'Server error encountered. Please try again shortly.', statusCode }
      }

      return { message: `Request failed with status code ${statusCode}`, statusCode }
    } else if (err.request) {
      return {
        message: 'Unable to connect. Check your connection and try again.',
      }
    }
  }

  return {
    message: (err as Error)?.message || 'An unexpected error occurred. Please try again.',
  }
}

/**
 * POST register endpoint
 */
export async function registerApi(payload: RegisterPayload): Promise<AuthResponse> {
  const response = await apiClient.post<AuthResponse>(AUTH_CONFIG.endpoints.register, {
    full_name: payload.full_name,
    email: payload.email,
    password: payload.password,
  })

  const token = response.data.access_token || response.data.access
  if (token) {
    setAccessToken(token)
  }

  return response.data
}

/**
 * POST login endpoint
 */
export async function loginApi(payload: LoginPayload): Promise<AuthResponse> {
  const response = await apiClient.post<AuthResponse>(AUTH_CONFIG.endpoints.login, {
    email: payload.email,
    password: payload.password,
    remember_me: payload.remember_me ?? false,
  })

  const token = response.data.access_token || response.data.access
  if (token) {
    setAccessToken(token)
  }

  return response.data
}

/**
 * POST refresh endpoint
 */
export async function refreshApi(): Promise<AuthResponse> {
  const response = await apiClient.post<AuthResponse>(AUTH_CONFIG.endpoints.refresh, {})

  const token = response.data.access_token || response.data.access
  if (token) {
    setAccessToken(token)
  }

  return response.data
}

/**
 * POST logout endpoint
 */
export async function logoutApi(): Promise<{ detail?: string }> {
  try {
    const response = await apiClient.post<{ detail?: string }>(AUTH_CONFIG.endpoints.logout, {})
    return response.data
  } finally {
    setAccessToken(null)
  }
}

/**
 * GET current authenticated user endpoint
 */
export async function getCurrentUserApi(): Promise<User> {
  const response = await apiClient.get<User>(AUTH_CONFIG.endpoints.me)
  return response.data
}

/** Request a password reset without revealing whether the email is registered. */
export async function requestPasswordResetApi(email: string): Promise<{ message: string }> {
  const response = await apiClient.post<{ message: string }>(`${AUTH_CONFIG.apiPrefix}/auth/password-reset/`, { email })
  return response.data
}

/** Consume a single-use reset link and set the account's new password. */
export async function confirmPasswordResetApi(payload: {
  uid: string
  token: string
  password: string
}): Promise<{ message: string }> {
  const response = await apiClient.post<{ message: string }>(`${AUTH_CONFIG.apiPrefix}/auth/password-reset/confirm/`, payload)
  return response.data
}

// Aliases for convenience
export const getMeApi = getCurrentUserApi
export const authService = {
  register: registerApi,
  login: loginApi,
  refresh: refreshApi,
  logout: logoutApi,
  getCurrentUser: getCurrentUserApi,
}
