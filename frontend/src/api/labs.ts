import apiClient from './client'
import type { Lab, LabSession, LabTask, TaskCheckResult, LabScore } from '@/types'

export const labsApi = {
  list: () => apiClient.get<Lab[]>('/labs').then(r => r.data),

  get: (id: string) => apiClient.get<Lab>(`/labs/${id}`).then(r => r.data),

  getTasks: (labId: string) =>
    apiClient.get<LabTask[]>(`/labs/${labId}/tasks`).then(r => r.data),

  startSession: (labId: string) =>
    apiClient.post<LabSession>('/labs/sessions', { lab_id: labId }).then(r => r.data),

  stopSession: (sessionId: string) =>
    apiClient.delete(`/labs/sessions/${sessionId}`),

  getSession: (sessionId: string) =>
    apiClient.get<LabSession>(`/labs/sessions/${sessionId}`).then(r => r.data),

  checkTask: (sessionId: string, taskId: string) =>
    apiClient
      .post<TaskCheckResult>(`/labs/sessions/${sessionId}/check-task`, { task_id: taskId })
      .then(r => r.data),

  submitLab: (sessionId: string) =>
    apiClient.post<LabScore>(`/labs/sessions/${sessionId}/submit`).then(r => r.data),

  /** Returns a WebSocket URL with auth token embedded */
  terminalWsUrl: (sessionId: string, token: string) => {
    const protocol = window.location.protocol === 'https:' ? 'wss' : 'ws'
    return `${protocol}://${window.location.host}/api/v1/labs/sessions/${sessionId}/terminal?token=${token}`
  },
}
