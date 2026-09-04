import { describe, it, expect, vi, beforeEach } from 'vitest'
import { renderHook } from '@testing-library/react'
import { useSSE } from '../useSSE'

class MockEventSource {
  static instances: MockEventSource[] = []
  url: string
  onmessage: ((event: any) => void) | null = null
  onerror: ((error: any) => void) | null = null
  closed = false
  listeners: Record<string, Function[]> = {}

  constructor(url: string) {
    this.url = url
    MockEventSource.instances.push(this)
  }

  addEventListener(type: string, cb: Function) {
    this.listeners[type] = this.listeners[type] || []
    this.listeners[type].push(cb)
  }

  removeEventListener(type: string, cb: Function) {
    if (this.listeners[type]) {
      this.listeners[type] = this.listeners[type].filter(l => l !== cb)
    }
  }

  emit(type: string, data: any) {
    const event = { type, data: typeof data === 'string' ? data : JSON.stringify(data) }
    const list = this.listeners[type] || []
    list.forEach(cb => cb(event))
    if (this.onmessage) {
      this.onmessage(event)
    }
  }

  close() {
    this.closed = true
  }
}

describe('useSSE', () => {
  beforeEach(() => {
    MockEventSource.instances = []
    vi.stubGlobal('EventSource', MockEventSource)
  })

  it('does nothing when url is null', () => {
    renderHook(() => useSSE(null, {}))
    expect(MockEventSource.instances).toHaveLength(0)
  })

  it('initializes EventSource and dispatches init, progress, done, error events', () => {
    const onInit = vi.fn()
    const onProgress = vi.fn()
    const onDone = vi.fn()
    const onError = vi.fn()

    const { unmount } = renderHook(() =>
      useSSE('http://localhost:8000/api/stream', { onInit, onProgress, onDone, onError })
    )

    expect(MockEventSource.instances).toHaveLength(1)
    const es = MockEventSource.instances[0]
    expect(es.url).toBe('http://localhost:8000/api/stream')

    // Simulate init event
    es.emit('init', { status: 'running', progress: 5 })
    expect(onInit).toHaveBeenCalledWith({ status: 'running', progress: 5 })

    // Simulate progress event
    es.emit('progress', { step: 'extract', progress: 10 })
    expect(onProgress).toHaveBeenCalledWith({ step: 'extract', progress: 10 })

    // Simulate done event
    es.emit('done', { count: 3 })
    expect(onDone).toHaveBeenCalledWith({ count: 3 })

    // Simulate error event
    es.emit('error', { message: 'failed' })
    expect(onError).toHaveBeenCalledWith({ message: 'failed' })

    // Simulate invalid json
    es.onmessage?.({ data: 'invalid json' } as any)

    // Cleanup on unmount
    unmount()
    expect(es.closed).toBe(true)
  })
})
