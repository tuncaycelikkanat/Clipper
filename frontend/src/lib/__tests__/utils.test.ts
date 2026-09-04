import { describe, it, expect } from 'vitest'
import { cn, formatDuration } from '../utils'

describe('utils', () => {
  describe('cn', () => {
    it('merges class names correctly', () => {
      expect(cn('bg-red-500', 'text-white')).toBe('bg-red-500 text-white')
      expect(cn('p-4', false && 'hidden', 'm-2')).toBe('p-4 m-2')
      expect(cn('px-2 py-1', 'px-4')).toBe('py-1 px-4')
    })
  })

  describe('formatDuration', () => {
    it('formats seconds into mm:ss format', () => {
      expect(formatDuration(0)).toBe('0:00')
      expect(formatDuration(45)).toBe('0:45')
      expect(formatDuration(65)).toBe('1:05')
      expect(formatDuration(600)).toBe('10:00')
      expect(formatDuration(3665)).toBe('61:05')
    })
  })
})
