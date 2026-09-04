import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { Button } from '../Button'
import { Badge } from '../Badge'
import { Card, CardHeader, CardTitle, CardContent } from '../Card'
import { Input } from '../Input'

describe('UI Components', () => {
  describe('Button', () => {
    it('renders with default variant and handles clicks', () => {
      const onClick = vi.fn()
      render(<Button onClick={onClick}>Click Me</Button>)
      const btn = screen.getByRole('button', { name: 'Click Me' })
      expect(btn).toBeInTheDocument()
      expect(btn).toHaveClass('bg-violet-600')
      fireEvent.click(btn)
      expect(onClick).toHaveBeenCalledTimes(1)
    })

    it('renders all variants and sizes', () => {
      const { rerender } = render(<Button variant="destructive" size="sm">Destructive</Button>)
      expect(screen.getByRole('button')).toHaveClass('bg-destructive')
      expect(screen.getByRole('button')).toHaveClass('h-9')

      rerender(<Button variant="outline" size="lg">Outline</Button>)
      expect(screen.getByRole('button')).toHaveClass('border-input')
      expect(screen.getByRole('button')).toHaveClass('h-11')

      rerender(<Button variant="secondary" size="icon">Sec</Button>)
      expect(screen.getByRole('button')).toHaveClass('bg-secondary')
      expect(screen.getByRole('button')).toHaveClass('h-10 w-10')

      rerender(<Button variant="ghost">Ghost</Button>)
      expect(screen.getByRole('button')).toHaveClass('hover:bg-accent')
    })
  })

  describe('Badge', () => {
    it('renders all badge variants', () => {
      const { rerender } = render(<Badge variant="default">Default</Badge>)
      expect(screen.getByText('Default')).toHaveClass('bg-violet-600')

      rerender(<Badge variant="secondary">Sec</Badge>)
      expect(screen.getByText('Sec')).toHaveClass('bg-secondary')

      rerender(<Badge variant="destructive">Dest</Badge>)
      expect(screen.getByText('Dest')).toHaveClass('bg-destructive')

      rerender(<Badge variant="success">Succ</Badge>)
      expect(screen.getByText('Succ')).toHaveClass('text-green-500')

      rerender(<Badge variant="warning">Warn</Badge>)
      expect(screen.getByText('Warn')).toHaveClass('text-yellow-500')

      rerender(<Badge variant="outline">Out</Badge>)
      expect(screen.getByText('Out')).toHaveClass('text-foreground')
    })
  })

  describe('Card', () => {
    it('renders Card with header, title and content', () => {
      render(
        <Card className="custom-card">
          <CardHeader>
            <CardTitle>Card Title</CardTitle>
          </CardHeader>
          <CardContent>Card Content Body</CardContent>
        </Card>
      )
      expect(screen.getByText('Card Title')).toBeInTheDocument()
      expect(screen.getByText('Card Content Body')).toBeInTheDocument()
    })
  })

  describe('Input', () => {
    it('renders input and handles change events', () => {
      const onChange = vi.fn()
      render(<Input placeholder="Enter text" onChange={onChange} />)
      const input = screen.getByPlaceholderText('Enter text')
      fireEvent.change(input, { target: { value: 'Hello' } })
      expect(onChange).toHaveBeenCalled()
      expect((input as HTMLInputElement).value).toBe('Hello')
    })
  })
})
