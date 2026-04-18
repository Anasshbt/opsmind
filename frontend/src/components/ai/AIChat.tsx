/**
 * AI Chat panel embedded inside the lab workspace.
 * Uses SSE (server-sent events) for streamed token delivery.
 */
import { useState, useRef, useEffect, useCallback } from 'react'
import { Send, Loader2, Bot, User, Lightbulb, Bug, HelpCircle } from 'lucide-react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { useAuthStore } from '@/store/auth'
import type { AssistantMode, ChatMessage } from '@/types'

interface AIChatProps {
  labTitle?: string
  terminalOutput?: string
}

const QUICK_ACTIONS = [
  { icon: Lightbulb, label: 'Hint', mode: 'hint' as AssistantMode },
  { icon: Bug, label: 'Debug', mode: 'debug' as AssistantMode },
  { icon: HelpCircle, label: 'Explain', mode: 'explain' as AssistantMode },
]

export function AIChat({ labTitle, terminalOutput }: AIChatProps) {
  const [messages, setMessages] = useState<ChatMessage[]>([
    {
      role: 'assistant',
      content: `Hi! I'm your DevOps AI assistant. I can help you with commands, debug errors, or give hints. What do you need?`,
      timestamp: new Date(),
    },
  ])
  const [input, setInput] = useState('')
  const [isStreaming, setIsStreaming] = useState(false)
  const [activeMode, setActiveMode] = useState<AssistantMode>('general')
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const { accessToken } = useAuthStore()

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  const sendMessage = useCallback(async (text?: string, mode?: AssistantMode) => {
    const content = text ?? input.trim()
    if (!content || isStreaming) return

    const userMsg: ChatMessage = { role: 'user', content, timestamp: new Date() }
    setMessages(prev => [...prev, userMsg])
    setInput('')
    setIsStreaming(true)

    // Add empty assistant message for streaming
    const assistantMsg: ChatMessage = { role: 'assistant', content: '', timestamp: new Date() }
    setMessages(prev => [...prev, assistantMsg])

    try {
      const endpoint = mode === 'hint' ? '/api/v1/ai/hint'
        : mode === 'debug' ? '/api/v1/ai/debug'
        : mode === 'explain' ? '/api/v1/ai/explain'
        : '/api/v1/ai/chat'

      const body = mode === 'hint'
        ? { lab_title: labTitle ?? '', task_description: content, terminal_history: terminalOutput ?? '' }
        : mode === 'debug'
        ? { error_output: terminalOutput ?? content }
        : mode === 'explain'
        ? { command: content }
        : {
            message: content,
            mode: activeMode,
            context: terminalOutput ? `Terminal output:\n${terminalOutput.slice(-1500)}` : undefined,
            history: messages.slice(-8).map(m => ({ role: m.role, content: m.content })),
          }

      const response = await fetch(endpoint, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${accessToken}`,
        },
        body: JSON.stringify(body),
      })

      if (!response.ok) throw new Error(`HTTP ${response.status}`)

      const reader = response.body!.getReader()
      const decoder = new TextDecoder()
      let accumulated = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        const chunk = decoder.decode(value, { stream: true })
        const lines = chunk.split('\n')

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            const token = line.slice(6)
            if (token === '[DONE]') continue
            accumulated += token
            setMessages(prev => {
              const updated = [...prev]
              updated[updated.length - 1] = {
                ...updated[updated.length - 1],
                content: accumulated,
              }
              return updated
            })
          }
        }
      }
    } catch (err) {
      setMessages(prev => {
        const updated = [...prev]
        updated[updated.length - 1] = {
          ...updated[updated.length - 1],
          content: 'Sorry, I encountered an error. Please try again.',
        }
        return updated
      })
    } finally {
      setIsStreaming(false)
    }
  }, [input, isStreaming, activeMode, messages, labTitle, terminalOutput, accessToken])

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="p-4 border-b border-gray-800 flex items-center gap-2">
        <div className="w-8 h-8 rounded-full bg-brand-600/20 flex items-center justify-center">
          <Bot className="w-4 h-4 text-brand-400" />
        </div>
        <div>
          <p className="text-sm font-semibold text-white">OpsMind AI</p>
          <p className="text-xs text-gray-500">DevOps Assistant</p>
        </div>
      </div>

      {/* Quick actions */}
      <div className="flex gap-2 p-3 border-b border-gray-800">
        {QUICK_ACTIONS.map(({ icon: Icon, label, mode }) => (
          <button
            key={mode}
            onClick={() => sendMessage(label === 'Hint' ? 'Give me a hint' : label === 'Debug' ? 'Debug my last error' : undefined, mode)}
            disabled={isStreaming}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs
                       bg-gray-800 hover:bg-gray-700 text-gray-300 transition-colors
                       disabled:opacity-50"
          >
            <Icon className="w-3 h-3" />
            {label}
          </button>
        ))}
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {messages.map((msg, idx) => (
          <div key={idx} className={`flex gap-3 ${msg.role === 'user' ? 'justify-end' : ''}`}>
            {msg.role === 'assistant' && (
              <div className="w-7 h-7 rounded-full bg-brand-600/20 flex items-center justify-center flex-shrink-0 mt-1">
                <Bot className="w-3.5 h-3.5 text-brand-400" />
              </div>
            )}
            <div
              className={`max-w-[85%] rounded-2xl px-4 py-2.5 text-sm
                ${msg.role === 'user'
                  ? 'bg-brand-600 text-white rounded-tr-none'
                  : 'bg-gray-800 text-gray-200 rounded-tl-none'
                }`}
            >
              {msg.role === 'assistant' ? (
                <div className="prose prose-invert prose-sm max-w-none">
                  <ReactMarkdown remarkPlugins={[remarkGfm]}>{msg.content}</ReactMarkdown>
                  {isStreaming && idx === messages.length - 1 && (
                    <span className="inline-block w-1.5 h-4 bg-brand-400 animate-pulse ml-0.5 align-middle" />
                  )}
                </div>
              ) : (
                <p>{msg.content}</p>
              )}
            </div>
            {msg.role === 'user' && (
              <div className="w-7 h-7 rounded-full bg-gray-700 flex items-center justify-center flex-shrink-0 mt-1">
                <User className="w-3.5 h-3.5 text-gray-400" />
              </div>
            )}
          </div>
        ))}
        <div ref={messagesEndRef} />
      </div>

      {/* Input */}
      <div className="p-4 border-t border-gray-800">
        <div className="flex gap-2">
          <input
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMessage() } }}
            placeholder="Ask anything about DevOps..."
            disabled={isStreaming}
            className="flex-1 bg-gray-800 border border-gray-700 rounded-xl px-4 py-2.5
                       text-sm text-white placeholder-gray-500 focus:outline-none
                       focus:border-brand-500 disabled:opacity-50"
          />
          <button
            onClick={() => sendMessage()}
            disabled={!input.trim() || isStreaming}
            className="w-10 h-10 rounded-xl bg-brand-600 hover:bg-brand-500 text-white
                       flex items-center justify-center transition-colors disabled:opacity-50"
          >
            {isStreaming ? <Loader2 className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4" />}
          </button>
        </div>
      </div>
    </div>
  )
}
