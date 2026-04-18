import { useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useQuery, useMutation } from '@tanstack/react-query'
import { Play, Loader2, AlertCircle, ArrowLeft } from 'lucide-react'
import toast from 'react-hot-toast'

import { LabWorkspace } from '@/components/lab/LabWorkspace'
import { labsApi } from '@/api/labs'

export function LabPage() {
  const { labId } = useParams<{ labId: string }>()
  const navigate = useNavigate()
  const [activeSession, setActiveSession] = useState<string | null>(null)

  const { data: lab, isLoading } = useQuery({
    queryKey: ['lab', labId],
    queryFn: () => labsApi.get(labId!),
    enabled: !!labId,
  })

  const startMutation = useMutation({
    mutationFn: () => labsApi.startSession(labId!),
    onSuccess: (session) => {
      setActiveSession(session.id)
      toast.success('Lab environment ready!')
    },
    onError: (err: any) => {
      toast.error(err.response?.data?.detail ?? 'Failed to start lab')
    },
  })

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-[calc(100vh-4rem)]">
        <Loader2 className="w-8 h-8 animate-spin text-brand-500" />
      </div>
    )
  }

  if (!lab) {
    return (
      <div className="flex flex-col items-center justify-center h-[calc(100vh-4rem)] gap-4">
        <AlertCircle className="w-12 h-12 text-red-400" />
        <p className="text-gray-400">Lab not found</p>
        <button onClick={() => navigate('/labs')} className="text-brand-400 hover:text-brand-300">
          ← Back to labs
        </button>
      </div>
    )
  }

  if (activeSession) {
    return <LabWorkspace labId={lab.id} sessionId={activeSession} />
  }

  return (
    <div className="max-w-3xl mx-auto px-4 py-12">
      <button
        onClick={() => navigate('/labs')}
        className="flex items-center gap-2 text-gray-400 hover:text-white mb-8 transition-colors"
      >
        <ArrowLeft className="w-4 h-4" /> Back to labs
      </button>

      <div className="bg-gray-900 rounded-2xl border border-gray-800 overflow-hidden">
        <div className="bg-gradient-to-r from-brand-900/50 to-gray-900 p-8">
          <h1 className="text-3xl font-bold text-white mb-3">{lab.title}</h1>
          <p className="text-gray-300">{lab.description}</p>
        </div>

        <div className="p-8 space-y-6">
          <div className="grid grid-cols-3 gap-4">
            {[
              { label: 'CPU', value: lab.cpu_limit },
              { label: 'Memory', value: lab.memory_limit },
              { label: 'Duration', value: `${Math.floor(lab.timeout_seconds / 60)} min` },
            ].map(({ label, value }) => (
              <div key={label} className="bg-gray-800 rounded-xl p-4 text-center">
                <p className="text-xs text-gray-500 uppercase tracking-wide mb-1">{label}</p>
                <p className="text-lg font-semibold text-white font-mono">{value}</p>
              </div>
            ))}
          </div>

          <button
            onClick={() => startMutation.mutate()}
            disabled={startMutation.isPending}
            className="w-full py-4 px-6 bg-brand-600 hover:bg-brand-500 text-white font-bold
                       text-lg rounded-xl transition-all hover:scale-[1.02] active:scale-100
                       disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-3"
          >
            {startMutation.isPending ? (
              <><Loader2 className="w-5 h-5 animate-spin" /> Starting environment...</>
            ) : (
              <><Play className="w-5 h-5" /> Launch Lab</>
            )}
          </button>

          <p className="text-xs text-center text-gray-600">
            Your environment will be automatically destroyed after the time limit.
            No root access. Network restrictions apply.
          </p>
        </div>
      </div>
    </div>
  )
}
