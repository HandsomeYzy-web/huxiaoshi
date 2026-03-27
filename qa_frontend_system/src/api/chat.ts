export interface ChatSession {
  id: number
  title: string
  created_at?: string
}

export interface ChatMessage {
  id?: number
  session_id: number
  role: 'user' | 'ai'
  content: string
  created_at?: string
}
