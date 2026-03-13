import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { PdfPreviewPane } from '../components/editor/components/PdfPreviewPane'
import React from 'react'

function makeProps(overrides: Partial<Parameters<typeof PdfPreviewPane>[0]> = {}) {
  return {
    iframeRef: React.createRef<HTMLIFrameElement>(),
    pdfViewerHtml: '<html><body>PDF</body></html>',
    compileStatus: 'idle' as const,
    compileError: null as string | null,
    compileLogs: [] as string[],
    lastCompileAt: null as number | null,
    ...overrides,
  }
}

beforeEach(() => {
  vi.useFakeTimers()
})
afterEach(() => {
  vi.useRealTimers()
})

/* ================================================================
   RECOMPILE BUTTON
   ================================================================ */

describe('PdfPreviewPane — Recompile', () => {
  it('shows recompile button when onCompile is provided', () => {
    render(<PdfPreviewPane {...makeProps({ onCompile: vi.fn() })} />)
    expect(screen.getByText('Recompile')).toBeInTheDocument()
  })

  it('does not show recompile button when onCompile is not provided', () => {
    render(<PdfPreviewPane {...makeProps()} />)
    expect(screen.queryByText('Recompile')).not.toBeInTheDocument()
  })

  it('calls onCompile when recompile button is clicked', () => {
    const onCompile = vi.fn()
    render(<PdfPreviewPane {...makeProps({ onCompile })} />)
    fireEvent.click(screen.getByText('Recompile'))
    expect(onCompile).toHaveBeenCalledOnce()
  })

  it('disables recompile button when compiling', () => {
    render(<PdfPreviewPane {...makeProps({ onCompile: vi.fn(), compileStatus: 'compiling' })} />)
    expect(screen.getByText('Recompile').closest('button')).toBeDisabled()
  })
})

/* ================================================================
   RELATIVE TIME DISPLAY
   ================================================================ */

describe('PdfPreviewPane — Updated Time', () => {
  it('shows seconds for recent compilations', () => {
    const now = Date.now()
    vi.setSystemTime(now)
    render(<PdfPreviewPane {...makeProps({ compileStatus: 'success', lastCompileAt: now - 5000 })} />)
    expect(screen.getByText(/Updated 5s ago/)).toBeInTheDocument()
  })

  it('shows minutes for compilations over 60s ago', () => {
    const now = Date.now()
    vi.setSystemTime(now)
    render(<PdfPreviewPane {...makeProps({ compileStatus: 'success', lastCompileAt: now - 180_000 })} />)
    expect(screen.getByText(/Updated 3m ago/)).toBeInTheDocument()
  })

  it('shows hours for compilations over 60min ago', () => {
    const now = Date.now()
    vi.setSystemTime(now)
    render(<PdfPreviewPane {...makeProps({ compileStatus: 'success', lastCompileAt: now - 7200_000 })} />)
    expect(screen.getByText(/Updated 2h ago/)).toBeInTheDocument()
  })

  it('shows minimum 1s even for just-now compilations', () => {
    const now = Date.now()
    vi.setSystemTime(now)
    render(<PdfPreviewPane {...makeProps({ compileStatus: 'success', lastCompileAt: now })} />)
    expect(screen.getByText(/Updated 1s ago/)).toBeInTheDocument()
  })

  it('does not show time when status is not success', () => {
    render(<PdfPreviewPane {...makeProps({ compileStatus: 'idle', lastCompileAt: Date.now() - 5000 })} />)
    expect(screen.queryByText(/Updated/)).not.toBeInTheDocument()
  })
})

/* ================================================================
   COMPILE STATUS DISPLAY
   ================================================================ */

describe('PdfPreviewPane — Status Display', () => {
  it('shows "Failed" when compile has an error', () => {
    render(<PdfPreviewPane {...makeProps({ compileStatus: 'error', compileError: 'Missing \\end{document}' })} />)
    expect(screen.getByText('Failed')).toBeInTheDocument()
  })

  it('does not show status text when idle with no lastCompileAt', () => {
    render(<PdfPreviewPane {...makeProps({ compileStatus: 'idle' })} />)
    expect(screen.queryByText(/Updated/)).not.toBeInTheDocument()
    expect(screen.queryByText('Failed')).not.toBeInTheDocument()
  })
})

/* ================================================================
   ZOOM CONTROLS
   ================================================================ */

describe('PdfPreviewPane — Zoom Controls', () => {
  it('shows default zoom level of 100%', () => {
    render(<PdfPreviewPane {...makeProps({ onCompile: vi.fn() })} />)
    expect(screen.getByText('100%')).toBeInTheDocument()
  })

  it('increments zoom on zoom in click', () => {
    render(<PdfPreviewPane {...makeProps({ onCompile: vi.fn() })} />)
    fireEvent.click(screen.getByTitle('Zoom in'))
    expect(screen.getByText('125%')).toBeInTheDocument()
  })

  it('decrements zoom on zoom out click', () => {
    render(<PdfPreviewPane {...makeProps({ onCompile: vi.fn() })} />)
    fireEvent.click(screen.getByTitle('Zoom out'))
    expect(screen.getByText('75%')).toBeInTheDocument()
  })

  it('opens zoom dropdown with presets', () => {
    render(<PdfPreviewPane {...makeProps({ onCompile: vi.fn() })} />)
    fireEvent.click(screen.getByText('100%'))
    expect(screen.getByText('50%')).toBeInTheDocument()
    expect(screen.getByText('75%')).toBeInTheDocument()
    expect(screen.getByText('125%')).toBeInTheDocument()
    expect(screen.getByText('150%')).toBeInTheDocument()
    expect(screen.getByText('Fit width')).toBeInTheDocument()
  })

  it('sets zoom to preset value when clicked', () => {
    render(<PdfPreviewPane {...makeProps({ onCompile: vi.fn() })} />)
    fireEvent.click(screen.getByText('100%'))
    fireEvent.click(screen.getByText('150%'))
    // The button text should now show 150%
    expect(screen.getByText('150%')).toBeInTheDocument()
  })

  it('disables zoom out at minimum', () => {
    render(<PdfPreviewPane {...makeProps({ onCompile: vi.fn() })} />)
    // Zoom out from 100 to 25 (minimum). Step is 25, so: 75, 50, 25.
    for (let i = 0; i < 3; i++) fireEvent.click(screen.getByTitle('Zoom out'))
    expect(screen.getByText('25%')).toBeInTheDocument()
    // At 25 (ZOOM_MIN), the button should be disabled
    expect(screen.getByTitle('Zoom out')).toBeDisabled()
  })
})

/* ================================================================
   INVERT COLORS
   ================================================================ */

describe('PdfPreviewPane — Invert Colors', () => {
  it('toggles invert colors on click', () => {
    render(<PdfPreviewPane {...makeProps({ onCompile: vi.fn() })} />)
    const btn = screen.getByTitle('Invert colors (dark reading mode)')
    // Initially not active
    expect(btn.className).not.toContain('bg-indigo-100')
    fireEvent.click(btn)
    // After click should be active
    expect(btn.className).toContain('bg-indigo-100')
    fireEvent.click(btn)
    // Toggled back off
    expect(btn.className).not.toContain('bg-indigo-100')
  })
})

/* ================================================================
   LOGS PANEL
   ================================================================ */

describe('PdfPreviewPane — Logs', () => {
  it('shows logs toggle button', () => {
    render(<PdfPreviewPane {...makeProps({ onCompile: vi.fn() })} />)
    expect(screen.getByTitle('Toggle compile logs')).toBeInTheDocument()
  })

  it('opens logs panel on toggle click', () => {
    render(<PdfPreviewPane {...makeProps({ onCompile: vi.fn(), compileStatus: 'success', compileLogs: ['This is a log line'] })} />)
    fireEvent.click(screen.getByTitle('Toggle compile logs'))
    expect(screen.getByText('No entries matching this filter')).toBeInTheDocument()
  })

  it('shows error count badge when there are errors', () => {
    const logs = ['! Missing $ inserted.', 'l.42 some context']
    render(<PdfPreviewPane {...makeProps({ onCompile: vi.fn(), compileLogs: logs })} />)
    // Error badge should appear on the logs button
    const badge = screen.getByTitle('Toggle compile logs').querySelector('span')
    expect(badge).not.toBeNull()
    expect(badge!.textContent).toBe('1')
  })

  it('shows compact error indicator when logs panel is closed', () => {
    const logs = ['! Missing $ inserted.']
    render(<PdfPreviewPane {...makeProps({ onCompile: vi.fn(), compileLogs: logs })} />)
    // Compact indicator should show
    expect(screen.getByText(/error/)).toBeInTheDocument()
    expect(screen.getByText('Click to view logs')).toBeInTheDocument()
  })

  it('opens logs panel from compact indicator', () => {
    const logs = ['! Missing $ inserted.']
    render(<PdfPreviewPane {...makeProps({ onCompile: vi.fn(), compileLogs: logs })} />)
    fireEvent.click(screen.getByText('Click to view logs'))
    // Log entries should now be visible
    expect(screen.getByText(/Missing \$ inserted/)).toBeInTheDocument()
  })

  it('shows filter tabs with correct counts', () => {
    const logs = [
      '! Missing $ inserted.',
      'LaTeX Warning: Citation undefined',
      'Overfull \\hbox in paragraph',
    ]
    render(<PdfPreviewPane {...makeProps({ onCompile: vi.fn(), compileLogs: logs })} />)
    fireEvent.click(screen.getByTitle('Toggle compile logs'))

    expect(screen.getByText('All logs')).toBeInTheDocument()
    expect(screen.getByText('Errors')).toBeInTheDocument()
    expect(screen.getByText('Warnings')).toBeInTheDocument()
    expect(screen.getByText('Info')).toBeInTheDocument()
  })

  it('filters to errors only', () => {
    const logs = [
      '! Missing $ inserted.',
      'LaTeX Warning: Citation undefined',
      'Overfull \\hbox in paragraph',
    ]
    render(<PdfPreviewPane {...makeProps({ onCompile: vi.fn(), compileLogs: logs })} />)
    fireEvent.click(screen.getByTitle('Toggle compile logs'))
    fireEvent.click(screen.getByText('Errors'))
    // Only error should be visible
    expect(screen.getByText(/Missing \$ inserted/)).toBeInTheDocument()
    expect(screen.queryByText(/Citation undefined/)).not.toBeInTheDocument()
  })

  it('shows raw logs section', () => {
    const logs = ['line 1', 'line 2', '! Error here']
    render(<PdfPreviewPane {...makeProps({ onCompile: vi.fn(), compileLogs: logs })} />)
    fireEvent.click(screen.getByTitle('Toggle compile logs'))
    expect(screen.getByText(/Raw logs.*3 lines/)).toBeInTheDocument()
  })

  it('expands raw logs on click', () => {
    const logs = ['line 1', 'line 2', '! Error here']
    render(<PdfPreviewPane {...makeProps({ onCompile: vi.fn(), compileLogs: logs })} />)
    fireEvent.click(screen.getByTitle('Toggle compile logs'))
    fireEvent.click(screen.getByText(/Raw logs/))
    // Raw logs render inside a <pre> element with newline-joined content
    const pre = document.querySelector('pre.font-mono')
    expect(pre).not.toBeNull()
    expect(pre!.textContent).toBe('line 1\nline 2\n! Error here')
  })
})

/* ================================================================
   AUTO-COMPILE DROPDOWN
   ================================================================ */

describe('PdfPreviewPane — Auto Compile', () => {
  it('shows auto compile toggle in dropdown', () => {
    const onToggleAutoCompile = vi.fn()
    render(<PdfPreviewPane {...makeProps({ onCompile: vi.fn(), onToggleAutoCompile })} />)
    // Click the dropdown chevron (second button in the compile group)
    const buttons = screen.getByText('Recompile').closest('div')!.querySelectorAll('button')
    fireEvent.click(buttons[1]) // chevron button
    expect(screen.getByText('Auto Compile')).toBeInTheDocument()
  })

  it('shows ON when autoCompileEnabled is true', () => {
    render(<PdfPreviewPane {...makeProps({ onCompile: vi.fn(), onToggleAutoCompile: vi.fn(), autoCompileEnabled: true })} />)
    const buttons = screen.getByText('Recompile').closest('div')!.querySelectorAll('button')
    fireEvent.click(buttons[1])
    expect(screen.getByText('ON')).toBeInTheDocument()
  })

  it('shows OFF when autoCompileEnabled is false', () => {
    render(<PdfPreviewPane {...makeProps({ onCompile: vi.fn(), onToggleAutoCompile: vi.fn(), autoCompileEnabled: false })} />)
    const buttons = screen.getByText('Recompile').closest('div')!.querySelectorAll('button')
    fireEvent.click(buttons[1])
    expect(screen.getByText('OFF')).toBeInTheDocument()
  })

  it('calls onToggleAutoCompile when clicked', () => {
    const onToggleAutoCompile = vi.fn()
    render(<PdfPreviewPane {...makeProps({ onCompile: vi.fn(), onToggleAutoCompile })} />)
    const buttons = screen.getByText('Recompile').closest('div')!.querySelectorAll('button')
    fireEvent.click(buttons[1])
    fireEvent.click(screen.getByText('Auto Compile'))
    expect(onToggleAutoCompile).toHaveBeenCalledOnce()
  })
})
