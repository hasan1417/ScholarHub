import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { AiToolsMenu } from '../components/editor/components/AiToolsMenu'

function makeProps(overrides: Partial<Parameters<typeof AiToolsMenu>[0]> = {}) {
  return {
    readOnly: false,
    hasTextSelected: true,
    aiActionLoading: null as string | null,
    onAiAction: vi.fn(),
    ...overrides,
  }
}

/* ================================================================
   BUTTON STATE
   ================================================================ */

describe('AiToolsMenu — Button State', () => {
  it('is disabled when readOnly', () => {
    render(<AiToolsMenu {...makeProps({ readOnly: true })} />)
    // readOnly + hasTextSelected = disabled but title stays "AI text tools"
    const btn = screen.getByTitle('AI text tools')
    expect(btn).toBeDisabled()
  })

  it('is disabled when no text is selected', () => {
    render(<AiToolsMenu {...makeProps({ hasTextSelected: false })} />)
    const btn = screen.getByTitle('Select text first')
    expect(btn).toBeDisabled()
  })

  it('is enabled when text is selected and not readOnly', () => {
    render(<AiToolsMenu {...makeProps()} />)
    const btn = screen.getByTitle('AI text tools')
    expect(btn).not.toBeDisabled()
  })

  it('shows loading title when aiActionLoading is set', () => {
    render(<AiToolsMenu {...makeProps({ aiActionLoading: 'paraphrase' })} />)
    expect(screen.getByTitle('Processing: paraphrase...')).toBeInTheDocument()
  })
})

/* ================================================================
   DROPDOWN OPEN / CLOSE
   ================================================================ */

describe('AiToolsMenu — Dropdown', () => {
  it('opens menu on click', () => {
    render(<AiToolsMenu {...makeProps()} />)
    fireEvent.click(screen.getByTitle('AI text tools'))
    expect(screen.getByText('Paraphrase')).toBeInTheDocument()
    expect(screen.getByText('Summarize')).toBeInTheDocument()
    expect(screen.getByText('Explain')).toBeInTheDocument()
    expect(screen.getByText('Synonyms')).toBeInTheDocument()
    expect(screen.getByText('Change Tone...')).toBeInTheDocument()
  })

  it('does not open menu when readOnly', () => {
    render(<AiToolsMenu {...makeProps({ readOnly: true })} />)
    // Button is disabled, click should not open menu
    fireEvent.click(screen.getByTitle('AI text tools'))
    expect(screen.queryByText('Paraphrase')).not.toBeInTheDocument()
  })
})

/* ================================================================
   ACTION CALLBACKS
   ================================================================ */

describe('AiToolsMenu — Actions', () => {
  it('calls onAiAction("paraphrase") when Paraphrase is clicked', () => {
    const onAiAction = vi.fn()
    render(<AiToolsMenu {...makeProps({ onAiAction })} />)
    fireEvent.click(screen.getByTitle('AI text tools'))
    fireEvent.click(screen.getByText('Paraphrase'))
    expect(onAiAction).toHaveBeenCalledWith('paraphrase')
  })

  it('calls onAiAction("summarize") when Summarize is clicked', () => {
    const onAiAction = vi.fn()
    render(<AiToolsMenu {...makeProps({ onAiAction })} />)
    fireEvent.click(screen.getByTitle('AI text tools'))
    fireEvent.click(screen.getByText('Summarize'))
    expect(onAiAction).toHaveBeenCalledWith('summarize')
  })

  it('calls onAiAction("explain") when Explain is clicked', () => {
    const onAiAction = vi.fn()
    render(<AiToolsMenu {...makeProps({ onAiAction })} />)
    fireEvent.click(screen.getByTitle('AI text tools'))
    fireEvent.click(screen.getByText('Explain'))
    expect(onAiAction).toHaveBeenCalledWith('explain')
  })

  it('calls onAiAction("synonyms") when Synonyms is clicked', () => {
    const onAiAction = vi.fn()
    render(<AiToolsMenu {...makeProps({ onAiAction })} />)
    fireEvent.click(screen.getByTitle('AI text tools'))
    fireEvent.click(screen.getByText('Synonyms'))
    expect(onAiAction).toHaveBeenCalledWith('synonyms')
  })
})

/* ================================================================
   LOADING STATE
   ================================================================ */

describe('AiToolsMenu — Loading State', () => {
  it('disables all action buttons when an action is loading', () => {
    render(<AiToolsMenu {...makeProps({ aiActionLoading: 'paraphrase' })} />)
    // Menu stays open during loading
    const buttons = screen.getAllByRole('button')
    // Filter to action buttons inside the dropdown (not the trigger)
    const actionButtons = buttons.filter(b => {
      const text = b.textContent || ''
      return ['Paraphrase', 'Summarize', 'Explain', 'Synonyms', 'Change Tone...'].some(a => text.includes(a))
    })
    actionButtons.forEach(btn => {
      expect(btn).toBeDisabled()
    })
  })

  it('does not call onAiAction when clicking a disabled action', () => {
    const onAiAction = vi.fn()
    render(<AiToolsMenu {...makeProps({ onAiAction, aiActionLoading: 'paraphrase' })} />)
    fireEvent.click(screen.getByText('Summarize'))
    // onAiAction should not have been called for 'summarize'
    expect(onAiAction).not.toHaveBeenCalledWith('summarize')
  })
})
