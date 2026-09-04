import '@testing-library/jest-dom/vitest'
import { afterEach, vi } from 'vitest'
import { cleanup } from '@testing-library/react'

afterEach(() => {
  cleanup()
  vi.clearAllMocks()
})

// Mock window.matchMedia if needed
Object.defineProperty(window, 'matchMedia', {
  writable: true,
  value: vi.fn().mockImplementation(query => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: vi.fn(),
    removeListener: vi.fn(),
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    dispatchEvent: vi.fn(),
  })),
})

class MockEventSource {
  url: string
  onmessage: ((event: any) => void) | null = null
  onerror: ((error: any) => void) | null = null
  closed = false
  listeners: Record<string, Function[]> = {}

  constructor(url: string) {
    this.url = url
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

  dispatchEvent(event: any) {
    const list = this.listeners[event.type] || []
    list.forEach(cb => cb(event))
    return true
  }

  close() {
    this.closed = true
  }
}

vi.stubGlobal('EventSource', MockEventSource)
