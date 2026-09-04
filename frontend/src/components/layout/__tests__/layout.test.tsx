import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import Sidebar from '../Sidebar'
import TopBar from '../TopBar'
import Layout from '../Layout'

vi.mock('@tanstack/react-router', () => ({
  Link: ({ children, to, className }: any) => <a href={to} className={className}>{children}</a>,
  useLocation: () => ({ pathname: '/analyze' }),
  Outlet: () => <div data-testid="outlet">Page Content</div>,
}))

describe('Layout Components', () => {
  it('renders Sidebar with all links and marks active link', () => {
    render(<Sidebar />)
    expect(screen.getByText('Clipper')).toBeInTheDocument()
    expect(screen.getByText('Dashboard')).toBeInTheDocument()
    
    // Check active link styling on Analiz (pathname is /analyze)
    const analyzeLink = screen.getByText('Analiz').closest('a')
    expect(analyzeLink).toHaveClass('text-violet-500')
  })

  it('renders TopBar with mapped title', () => {
    render(<TopBar />)
    expect(screen.getByText('Analiz')).toBeInTheDocument()
  })

  it('renders complete Layout with Sidebar, TopBar, and Outlet', () => {
    render(<Layout />)
    expect(screen.getByTestId('outlet')).toBeInTheDocument()
    expect(screen.getByText('Page Content')).toBeInTheDocument()
  })
})
