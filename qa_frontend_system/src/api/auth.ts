import request from '../utils/request'

export interface TokenResponse {
  access_token: string
  token_type: string
}

export interface UserInfo {
  id: number
  username: string
  email: string
  is_active: boolean
  is_admin: boolean
  permissions: string[]
}

export interface RegisterRequest {
  username: string
  email: string
  password: string
}

export interface LoginRequest {
  username: string
  password: string
}

export function register(data: RegisterRequest): Promise<UserInfo> {
  return request.post('/auth/register', data)
}

export function login(data: LoginRequest): Promise<TokenResponse> {
  return request.post('/auth/login', data)
}

export function getMe(): Promise<UserInfo> {
  return request.get('/auth/me')
}

