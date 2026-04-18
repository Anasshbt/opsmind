/**
 * Terminal component — wraps xterm.js and connects it to the backend
 * WebSocket relay for the user's lab container.
 *
 * Usage:
 *   <Terminal sessionId={session.id} token={accessToken} />
 */
import { useEffect, useRef, useCallback } from 'react'
import { Terminal as XTerm } from 'xterm'
import { FitAddon } from '@xterm/addon-fit'
import { WebLinksAddon } from '@xterm/addon-web-links'
import { labsApi } from '@/api/labs'
import 'xterm/css/xterm.css'

interface TerminalProps {
  sessionId: string
  token: string
  onData?: (data: string) => void  // hook for AI context
  className?: string
}

const XTERM_THEME = {
  background: '#0d1117',
  foreground: '#c9d1d9',
  cursor: '#58a6ff',
  cursorAccent: '#0d1117',
  black: '#484f58',
  red: '#ff7b72',
  green: '#3fb950',
  yellow: '#d29922',
  blue: '#58a6ff',
  magenta: '#bc8cff',
  cyan: '#39c5cf',
  white: '#b1bac4',
  brightBlack: '#6e7681',
  brightRed: '#ffa198',
  brightGreen: '#56d364',
  brightYellow: '#e3b341',
  brightBlue: '#79c0ff',
  brightMagenta: '#d2a8ff',
  brightCyan: '#56d4dd',
  brightWhite: '#f0f6fc',
}

export function Terminal({ sessionId, token, onData, className }: TerminalProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const termRef = useRef<XTerm | null>(null)
  const wsRef = useRef<WebSocket | null>(null)
  const fitAddonRef = useRef<FitAddon | null>(null)
  const dataBufferRef = useRef<string[]>([])

  const connect = useCallback(() => {
    if (!containerRef.current) return

    // Initialize xterm
    const term = new XTerm({
      theme: XTERM_THEME,
      fontFamily: '"JetBrains Mono", "Fira Code", monospace',
      fontSize: 14,
      lineHeight: 1.4,
      cursorBlink: true,
      cursorStyle: 'block',
      allowTransparency: false,
      scrollback: 5000,
    })

    const fitAddon = new FitAddon()
    const webLinksAddon = new WebLinksAddon()

    term.loadAddon(fitAddon)
    term.loadAddon(webLinksAddon)
    term.open(containerRef.current)
    fitAddon.fit()

    termRef.current = term
    fitAddonRef.current = fitAddon

    term.writeln('\x1b[1;32mOpsMind Lab Terminal\x1b[0m')
    term.writeln('\x1b[2mConnecting to your sandbox...\x1b[0m')

    // Connect WebSocket
    const wsUrl = labsApi.terminalWsUrl(sessionId, token)
    const ws = new WebSocket(wsUrl)
    ws.binaryType = 'arraybuffer'
    wsRef.current = ws

    ws.onopen = () => {
      term.writeln('\x1b[1;32m✓ Connected\x1b[0m\r\n')
      // Send initial terminal size
      const { cols, rows } = term
      ws.send(JSON.stringify({ type: 'resize', cols, rows }))
    }

    ws.onmessage = (event) => {
      if (typeof event.data === 'string') {
        if (event.data === 'ping') return  // heartbeat
        term.write(event.data)
        // Buffer recent output for AI context
        dataBufferRef.current.push(event.data)
        if (dataBufferRef.current.length > 500) dataBufferRef.current.shift()
        onData?.(event.data)
      } else {
        // Binary frames
        const bytes = new Uint8Array(event.data)
        term.write(bytes)
      }
    }

    ws.onerror = () => {
      term.writeln('\r\n\x1b[1;31m✗ Connection error\x1b[0m')
    }

    ws.onclose = (event) => {
      if (event.code === 4401) {
        term.writeln('\r\n\x1b[1;31m✗ Unauthorized\x1b[0m')
      } else if (event.code === 4404) {
        term.writeln('\r\n\x1b[1;31m✗ Session not found\x1b[0m')
      } else {
        term.writeln('\r\n\x1b[33mSession ended\x1b[0m')
      }
    }

    // Forward keystrokes to the container
    term.onData((data) => {
      if (ws.readyState === WebSocket.OPEN) {
        ws.send(data)
      }
    })

    // Handle terminal resize
    const resizeObserver = new ResizeObserver(() => {
      fitAddon.fit()
      if (ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ type: 'resize', cols: term.cols, rows: term.rows }))
      }
    })
    resizeObserver.observe(containerRef.current)

    return () => {
      resizeObserver.disconnect()
    }
  }, [sessionId, token, onData])

  useEffect(() => {
    const cleanup = connect()
    return () => {
      cleanup?.()
      wsRef.current?.close()
      termRef.current?.dispose()
    }
  }, [connect])

  /** Expose terminal buffer for AI context extraction */
  const getRecentOutput = useCallback((chars = 2000): string => {
    return dataBufferRef.current.join('').slice(-chars)
  }, [])

  return (
    <div
      ref={containerRef}
      className={`w-full h-full bg-[#0d1117] rounded-lg overflow-hidden ${className ?? ''}`}
      style={{ minHeight: '400px' }}
    />
  )
}
