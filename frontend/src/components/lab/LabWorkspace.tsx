/**
 * LabWorkspace — the main interactive lab view.
 *
 * Layout:
 *  ┌────────────────┬────────────────────────────────────┐
 *  │  Instructions  │           Terminal                 │
 *  │  + Tasks       │                                    │
 *  │  + AI Chat     │                                    │
 *  └────────────────┴────────────────────────────────────┘
 */
import { useState, useRef, useCallback } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { CheckCircle, Circle, Loader2, ChevronRight, Bot, X, Clock } from 'lucide-react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import toast from 'react-hot-toast'

import { Terminal } from './Terminal'
import { AIChat } from '../ai/AIChat'
import { labsApi } from '@/api/labs'
import { useAuthStore } from '@/store/auth'
import type { LabTask, TaskCheckResult } from '@/types'

interface LabWorkspaceProps {
  labId: string
  sessionId: string
}

export function LabWorkspace({ labId, sessionId }: LabWorkspaceProps) {
  const { accessToken } = useAuthStore()
  const [showAI, setShowAI] = useState(false)
  const [terminalOutput, setTerminalOutput] = useState('')
  const [taskResults, setTaskResults] = useState<Record<string, TaskCheckResult>>({})
  const queryClient = useQueryClient()

  const { data: lab } = useQuery({
    queryKey: ['lab', labId],
    queryFn: () => labsApi.get(labId),
  })

  const { data: tasks = [] } = useQuery({
    queryKey: ['lab-tasks', labId],
    queryFn: () => labsApi.getTasks(labId),
  })

  const { data: session } = useQuery({
    queryKey: ['session', sessionId],
    queryFn: () => labsApi.getSession(sessionId),
    refetchInterval: 30_000,
  })

  const checkTaskMutation = useMutation({
    mutationFn: (taskId: string) => labsApi.checkTask(sessionId, taskId),
    onSuccess: (result) => {
      setTaskResults(prev => ({ ...prev, [result.task_id]: result }))
      if (result.passed) {
        toast.success('Task completed! 🎉')
      } else {
        toast.error('Not quite — keep trying!')
      }
    },
  })

  const submitMutation = useMutation({
    mutationFn: () => labsApi.submitLab(sessionId),
    onSuccess: (score) => {
      toast.success(`Lab submitted! Score: ${score.final_score}/${score.max_points}`)
      queryClient.invalidateQueries({ queryKey: ['session', sessionId] })
    },
  })

  const handleTerminalData = useCallback((data: string) => {
    setTerminalOutput(prev => (prev + data).slice(-3000))
  }, [])

  const expiresAt = session?.expires_at ? new Date(session.expires_at) : null
  const minutesLeft = expiresAt
    ? Math.max(0, Math.floor((expiresAt.getTime() - Date.now()) / 60_000))
    : null

  return (
    <div className="flex h-[calc(100vh-4rem)] bg-gray-950 overflow-hidden">
      {/* ── Left Panel ─────────────────────────────────────────── */}
      <div className="w-96 flex flex-col border-r border-gray-800 bg-gray-900 overflow-hidden">
        {/* Header */}
        <div className="p-4 border-b border-gray-800">
          <h2 className="font-semibold text-white text-lg">{lab?.title}</h2>
          {minutesLeft !== null && (
            <div className={`flex items-center gap-1 text-sm mt-1 ${minutesLeft < 10 ? 'text-red-400' : 'text-gray-400'}`}>
              <Clock className="w-3.5 h-3.5" />
              <span>{minutesLeft}m remaining</span>
            </div>
          )}
        </div>

        {/* Tabs */}
        <div className="flex border-b border-gray-800">
          {['Instructions', 'Tasks'].map(tab => (
            <button
              key={tab}
              className="flex-1 py-2 text-sm font-medium text-gray-400 hover:text-white
                         border-b-2 border-transparent hover:border-brand-500 transition-colors"
            >
              {tab}
            </button>
          ))}
        </div>

        {/* Instructions */}
        <div className="flex-1 overflow-y-auto p-4 prose prose-invert prose-sm max-w-none">
          {lab?.instructions_md ? (
            <ReactMarkdown remarkPlugins={[remarkGfm]}>
              {lab.instructions_md}
            </ReactMarkdown>
          ) : (
            <p className="text-gray-500">No instructions provided.</p>
          )}
        </div>

        {/* Tasks */}
        <div className="border-t border-gray-800 p-4 space-y-2">
          <h3 className="text-sm font-semibold text-gray-300 uppercase tracking-wide">Tasks</h3>
          {tasks.map((task: LabTask) => {
            const result = taskResults[task.id]
            const isPassed = result?.passed
            const isChecking = checkTaskMutation.isPending && checkTaskMutation.variables === task.id

            return (
              <div
                key={task.id}
                className={`flex items-start gap-3 p-3 rounded-lg border transition-all
                  ${isPassed
                    ? 'border-brand-600 bg-brand-950/30'
                    : 'border-gray-700 bg-gray-800/50 hover:border-gray-600'
                  }`}
              >
                <div className="mt-0.5 flex-shrink-0">
                  {isPassed ? (
                    <CheckCircle className="w-4 h-4 text-brand-500" />
                  ) : (
                    <Circle className="w-4 h-4 text-gray-600" />
                  )}
                </div>
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium text-gray-200">{task.title}</p>
                  {task.description && (
                    <p className="text-xs text-gray-500 mt-0.5">{task.description}</p>
                  )}
                  <p className="text-xs text-brand-400 mt-1">{task.points} pts</p>
                </div>
                <button
                  onClick={() => checkTaskMutation.mutate(task.id)}
                  disabled={isChecking || isPassed}
                  className="flex-shrink-0 px-2 py-1 text-xs rounded bg-gray-700 hover:bg-gray-600
                             text-gray-300 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                >
                  {isChecking ? <Loader2 className="w-3 h-3 animate-spin" /> : 'Check'}
                </button>
              </div>
            )
          })}

          <button
            onClick={() => submitMutation.mutate()}
            disabled={submitMutation.isPending}
            className="w-full mt-3 py-2.5 px-4 bg-brand-600 hover:bg-brand-500 text-white
                       font-semibold rounded-lg transition-colors disabled:opacity-50
                       flex items-center justify-center gap-2"
          >
            {submitMutation.isPending ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : (
              <>Submit Lab <ChevronRight className="w-4 h-4" /></>
            )}
          </button>
        </div>
      </div>

      {/* ── Terminal ────────────────────────────────────────────── */}
      <div className="flex-1 flex flex-col overflow-hidden relative">
        <Terminal
          sessionId={sessionId}
          token={accessToken!}
          onData={handleTerminalData}
          className="flex-1"
        />

        {/* AI Toggle */}
        <button
          onClick={() => setShowAI(!showAI)}
          className="absolute bottom-6 right-6 w-12 h-12 rounded-full bg-brand-600
                     hover:bg-brand-500 text-white shadow-lg flex items-center justify-center
                     transition-all hover:scale-110 z-10"
          title="Ask AI Assistant"
        >
          {showAI ? <X className="w-5 h-5" /> : <Bot className="w-5 h-5" />}
        </button>
      </div>

      {/* ── AI Chat Panel ───────────────────────────────────────── */}
      {showAI && (
        <div className="w-96 border-l border-gray-800 bg-gray-900">
          <AIChat
            labTitle={lab?.title}
            terminalOutput={terminalOutput}
          />
        </div>
      )}
    </div>
  )
}
