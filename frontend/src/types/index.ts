// ── Auth ──────────────────────────────────────────────────────────────────────

export interface User {
  id: string
  email: string
  username: string
  full_name: string | null
  role: 'user' | 'admin' | 'enterprise'
  avatar_url: string | null
  is_active: boolean
}

export interface TokenResponse {
  access_token: string
  refresh_token: string
  token_type: string
  expires_in: number
}

// ── Courses ───────────────────────────────────────────────────────────────────

export type CourseDomain = 'devops' | 'kubernetes' | 'networking' | 'devsecops' | 'sre' | 'cloud'
export type Difficulty = 'beginner' | 'intermediate' | 'advanced'

export interface Course {
  id: string
  title: string
  slug: string
  description: string | null
  domain: CourseDomain
  difficulty: Difficulty
  is_published: boolean
  estimated_hours: number
}

export interface Module {
  id: string
  title: string
  order: number
  content_md: string | null
  is_published: boolean
}

export interface Enrollment {
  id: string
  course_id: string
  progress_pct: number
  completed: boolean
}

// ── Labs ──────────────────────────────────────────────────────────────────────

export interface Lab {
  id: string
  title: string
  slug: string
  description: string | null
  instructions_md: string | null
  image: string
  cpu_limit: string
  memory_limit: string
  timeout_seconds: number
}

export interface LabTask {
  id: string
  title: string
  description: string | null
  order: number
  points: number
}

export type LabSessionStatus = 'pending' | 'running' | 'stopping' | 'stopped' | 'failed' | 'expired'

export interface LabSession {
  id: string
  lab_id: string
  status: LabSessionStatus
  container_id: string | null
  expires_at: string | null
  started_at: string | null
  created_at: string
}

export interface TaskCheckResult {
  task_id: string
  passed: boolean
  points_earned: number
  output: string
}

export interface LabScore {
  total_points: number
  max_points: number
  final_score: number
  time_bonus: number
  attempts_penalty: number
  tasks_passed: number
  tasks_total: number
}

// ── Enterprise ────────────────────────────────────────────────────────────────

export interface Enterprise {
  id: string
  name: string
  slug: string
}

export type ChallengeStatus = 'draft' | 'active' | 'closed' | 'archived'

export interface Challenge {
  id: string
  title: string
  description: string | null
  status: ChallengeStatus
  duration_minutes: number
  lab_ids: string[]
}

export interface LeaderboardEntry {
  rank: number
  username: string
  total_score: number
  submitted_at: string | null
}

// ── AI ────────────────────────────────────────────────────────────────────────

export type AssistantMode = 'explain' | 'debug' | 'hint' | 'coach' | 'general'

export interface ChatMessage {
  role: 'user' | 'assistant'
  content: string
  timestamp: Date
}
