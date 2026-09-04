import { describe, it, expect } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import App from '../App'

describe('App', () => {
  it('renders root application without crashing', async () => {
    render(<App />)
    await waitFor(() => {
      expect(screen.getByText('Clipper')).toBeInTheDocument()
    })
  })
})
