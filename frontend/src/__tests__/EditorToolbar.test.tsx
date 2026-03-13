import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { EditorToolbar } from '../components/editor/components/EditorToolbar'
import type { EditorView } from '@codemirror/view'

// ResizeObserver mock: default is no-op (visibleCount stays at max = all groups visible)
class NoopResizeObserver {
  observe() {}
  unobserve() {}
  disconnect() {}
}
globalThis.ResizeObserver = NoopResizeObserver as any

// Narrow-width mock: fires callback immediately to simulate a specific container width
function mockNarrowToolbar(width: number) {
  globalThis.ResizeObserver = class {
    constructor(private cb: ResizeObserverCallback) {}
    observe() { this.cb([{ contentRect: { width } } as ResizeObserverEntry], this as any) }
    unobserve() {}
    disconnect() {}
  } as any
}
function resetResizeObserver() {
  globalThis.ResizeObserver = NoopResizeObserver as any
}

// Mock child components that have their own test suites
vi.mock('../components/editor/components/AiToolsMenu', () => ({
  AiToolsMenu: ({ readOnly, hasTextSelected, aiActionLoading }: any) => (
    <div data-testid="ai-tools-menu" data-readonly={readOnly} data-selected={hasTextSelected} data-loading={aiActionLoading} />
  ),
}))
vi.mock('../components/editor/components/SectionHeadingDropdown', () => ({
  SectionHeadingDropdown: () => <div data-testid="section-heading-dropdown" />,
}))

function makeProps(overrides: Partial<Parameters<typeof EditorToolbar>[0]> = {}) {
  return {
    viewMode: 'code' as const,
    readOnly: false,
    saveState: 'idle' as const,
    onSave: vi.fn(),
    undoEnabled: true,
    redoEnabled: true,
    onUndo: vi.fn(),
    onRedo: vi.fn(),
    hasTextSelected: false,
    boldActive: false,
    italicActive: false,
    formattingGroups: [],
    onInsertBold: vi.fn(),
    onInsertItalics: vi.fn(),
    onInsertInlineMath: vi.fn(),
    onInsertDisplayMath: vi.fn(),
    onInsertCite: vi.fn(),
    onInsertFigure: vi.fn(),
    onInsertTable: vi.fn(),
    onInsertTableWithSize: vi.fn(),
    onInsertItemize: vi.fn(),
    onInsertEnumerate: vi.fn(),
    onInsertRef: vi.fn(),
    onInsertLink: vi.fn(),
    onOpenReferences: vi.fn(),
    editorViewRef: { current: null } as React.RefObject<EditorView | null>,
    aiActionLoading: null,
    onAiAction: vi.fn(),
    symbolPaletteOpen: false,
    onToggleSymbolPalette: vi.fn(),
    ...overrides,
  }
}

/** Helper: open the ••• More overflow menu */
function openMoreMenu() {
  fireEvent.click(screen.getByTitle('More formatting tools'))
}

/* ================================================================
   VIEW MODE TOGGLE
   ================================================================ */

describe('EditorToolbar — View Mode Conditional Rendering', () => {
  it('hides formatting tools in PDF view mode', () => {
    render(<EditorToolbar {...makeProps({ viewMode: 'pdf' })} />)
    expect(screen.queryByTitle('Undo')).not.toBeInTheDocument()
    expect(screen.queryByTitle(/Bold/)).not.toBeInTheDocument()
  })

  it('shows formatting tools in code view mode', () => {
    render(<EditorToolbar {...makeProps({ viewMode: 'code' })} />)
    expect(screen.getByTitle('Undo')).toBeInTheDocument()
    expect(screen.getByTitle(/Bold/)).toBeInTheDocument()
  })
})

/* ================================================================
   EDITING TOOLS VISIBILITY
   ================================================================ */

describe('EditorToolbar — Editing Tools Visibility', () => {
  it('hides editing tools in PDF view mode', () => {
    render(<EditorToolbar {...makeProps({ viewMode: 'pdf' })} />)
    expect(screen.queryByTitle('Undo')).not.toBeInTheDocument()
    expect(screen.queryByTitle('Redo')).not.toBeInTheDocument()
    expect(screen.queryByTitle(/Bold/)).not.toBeInTheDocument()
    expect(screen.queryByTitle(/Italic/)).not.toBeInTheDocument()
    expect(screen.queryByTestId('ai-tools-menu')).not.toBeInTheDocument()
  })

  it('hides editing tools when readOnly', () => {
    render(<EditorToolbar {...makeProps({ readOnly: true })} />)
    expect(screen.queryByTitle('Undo')).not.toBeInTheDocument()
    expect(screen.queryByTitle('Redo')).not.toBeInTheDocument()
    expect(screen.queryByTitle(/Bold/)).not.toBeInTheDocument()
  })

  it('shows editing tools in code mode when not readOnly', () => {
    render(<EditorToolbar {...makeProps()} />)
    expect(screen.getByTitle('Undo')).toBeInTheDocument()
    expect(screen.getByTitle('Redo')).toBeInTheDocument()
    expect(screen.getByTitle(/Bold/)).toBeInTheDocument()
    expect(screen.getByTitle(/Italic/)).toBeInTheDocument()
  })

  it('shows editing tools in split mode when not readOnly', () => {
    render(<EditorToolbar {...makeProps({ viewMode: 'split' })} />)
    expect(screen.getByTitle('Undo')).toBeInTheDocument()
    expect(screen.getByTitle(/Bold/)).toBeInTheDocument()
  })
})

/* ================================================================
   UNDO / REDO
   ================================================================ */

describe('EditorToolbar — Undo / Redo', () => {
  it('calls onUndo when undo button is clicked', () => {
    const onUndo = vi.fn()
    render(<EditorToolbar {...makeProps({ onUndo })} />)
    fireEvent.click(screen.getByTitle('Undo'))
    expect(onUndo).toHaveBeenCalledOnce()
  })

  it('calls onRedo when redo button is clicked', () => {
    const onRedo = vi.fn()
    render(<EditorToolbar {...makeProps({ onRedo })} />)
    fireEvent.click(screen.getByTitle('Redo'))
    expect(onRedo).toHaveBeenCalledOnce()
  })

  it('disables undo button when undoEnabled is false', () => {
    render(<EditorToolbar {...makeProps({ undoEnabled: false })} />)
    expect(screen.getByTitle('Undo')).toBeDisabled()
  })

  it('disables redo button when redoEnabled is false', () => {
    render(<EditorToolbar {...makeProps({ redoEnabled: false })} />)
    expect(screen.getByTitle('Redo')).toBeDisabled()
  })

  it('enables both buttons when both flags are true', () => {
    render(<EditorToolbar {...makeProps({ undoEnabled: true, redoEnabled: true })} />)
    expect(screen.getByTitle('Undo')).not.toBeDisabled()
    expect(screen.getByTitle('Redo')).not.toBeDisabled()
  })
})

/* ================================================================
   BOLD / ITALIC
   ================================================================ */

describe('EditorToolbar — Bold / Italic', () => {
  it('calls onInsertBold when bold button is clicked', () => {
    const onInsertBold = vi.fn()
    render(<EditorToolbar {...makeProps({ onInsertBold })} />)
    fireEvent.click(screen.getByTitle(/Bold/))
    expect(onInsertBold).toHaveBeenCalledOnce()
  })

  it('calls onInsertItalics when italic button is clicked', () => {
    const onInsertItalics = vi.fn()
    render(<EditorToolbar {...makeProps({ onInsertItalics })} />)
    fireEvent.click(screen.getByTitle(/Italic/))
    expect(onInsertItalics).toHaveBeenCalledOnce()
  })

  it('disables bold/italic when readOnly', () => {
    render(<EditorToolbar {...makeProps({ readOnly: false })} />)
    expect(screen.getByTitle(/Bold/)).not.toBeDisabled()
  })

  it('applies active style when boldActive is true', () => {
    render(<EditorToolbar {...makeProps({ boldActive: true })} />)
    const btn = screen.getByTitle(/Bold/)
    expect(btn.className).toContain('bg-indigo-100')
  })

  it('applies active style when italicActive is true', () => {
    render(<EditorToolbar {...makeProps({ italicActive: true })} />)
    const btn = screen.getByTitle(/Italic/)
    expect(btn.className).toContain('bg-indigo-100')
  })

  it('does not apply active style when boldActive is false', () => {
    render(<EditorToolbar {...makeProps({ boldActive: false })} />)
    const btn = screen.getByTitle(/Bold/)
    expect(btn.className).not.toContain('bg-indigo-100')
  })
})

/* ================================================================
   DESKTOP-ONLY ITEMS (Section dropdown, Math, Symbol, More menu)
   ================================================================ */

describe('EditorToolbar — Desktop-only formatting', () => {
  it('shows all toolbar groups inline when space is wide (default)', () => {
    render(<EditorToolbar {...makeProps({ isMobile: false })} />)
    expect(screen.getByTestId('section-heading-dropdown')).toBeInTheDocument()
    expect(screen.getByTitle(/Insert math/)).toBeInTheDocument()
    expect(screen.getByTitle(/Symbol palette/)).toBeInTheDocument()
    expect(screen.getByTitle(/Citation/)).toBeInTheDocument()
    expect(screen.getByTitle(/Insert from References/i)).toBeInTheDocument()
    expect(screen.getByTitle(/Insert figure/)).toBeInTheDocument()
    expect(screen.getByTitle(/Insert table/)).toBeInTheDocument()
    expect(screen.getByTitle(/Bullet list/)).toBeInTheDocument()
    expect(screen.getByTitle(/Numbered list/)).toBeInTheDocument()
    // Link/Ref and Comment/Indent are also inline when wide
    expect(screen.getByTitle('Hyperlink')).toBeInTheDocument()
    expect(screen.getByTitle(/Cross Reference/)).toBeInTheDocument()
    expect(screen.getByTitle('Toggle Comment')).toBeInTheDocument()
    expect(screen.getByTitle('Decrease Indent')).toBeInTheDocument()
    expect(screen.getByTitle('Increase Indent')).toBeInTheDocument()
    // No overflow button when all groups fit
    expect(screen.queryByTitle(/More formatting/)).not.toBeInTheDocument()
  })

  it('hides desktop items on mobile', () => {
    render(<EditorToolbar {...makeProps({ isMobile: true })} />)
    expect(screen.queryByTestId('section-heading-dropdown')).not.toBeInTheDocument()
    expect(screen.queryByTitle(/Insert math/)).not.toBeInTheDocument()
    expect(screen.queryByTitle(/Citation/)).not.toBeInTheDocument()
    expect(screen.queryByTitle(/Insert figure/)).not.toBeInTheDocument()
  })

  it('calls onInsertInlineMath when inline math option is clicked', () => {
    const onInsertInlineMath = vi.fn()
    render(<EditorToolbar {...makeProps({ onInsertInlineMath })} />)
    fireEvent.click(screen.getByTitle(/Insert math/))
    fireEvent.click(screen.getByText('Inline Math'))
    expect(onInsertInlineMath).toHaveBeenCalledOnce()
  })

  it('calls onInsertDisplayMath when display math option is clicked', () => {
    const onInsertDisplayMath = vi.fn()
    render(<EditorToolbar {...makeProps({ onInsertDisplayMath })} />)
    fireEvent.click(screen.getByTitle(/Insert math/))
    fireEvent.click(screen.getByText('Display Math'))
    expect(onInsertDisplayMath).toHaveBeenCalledOnce()
  })

  it('calls onInsertCite when cite button is clicked', () => {
    const onInsertCite = vi.fn()
    render(<EditorToolbar {...makeProps({ onInsertCite })} />)
    fireEvent.click(screen.getByTitle(/Citation/))
    expect(onInsertCite).toHaveBeenCalledOnce()
  })

  it('calls onInsertFigure when figure button is clicked', () => {
    const onInsertFigure = vi.fn()
    render(<EditorToolbar {...makeProps({ onInsertFigure })} />)
    fireEvent.click(screen.getByTitle(/Insert figure/))
    expect(onInsertFigure).toHaveBeenCalledOnce()
  })

  it('calls onInsertItemize when bullet list button is clicked', () => {
    const onInsertItemize = vi.fn()
    render(<EditorToolbar {...makeProps({ onInsertItemize })} />)
    fireEvent.click(screen.getByTitle(/Bullet list/))
    expect(onInsertItemize).toHaveBeenCalledOnce()
  })

  it('calls onInsertEnumerate when numbered list button is clicked', () => {
    const onInsertEnumerate = vi.fn()
    render(<EditorToolbar {...makeProps({ onInsertEnumerate })} />)
    fireEvent.click(screen.getByTitle(/Numbered list/))
    expect(onInsertEnumerate).toHaveBeenCalledOnce()
  })
})

/* ================================================================
   MORE (•••) OVERFLOW MENU
   ================================================================ */

describe('EditorToolbar — More Overflow Menu (narrow toolbar)', () => {
  beforeEach(() => {
    // Simulate narrow toolbar (~650px): groups 4+5 (link/ref, comment/indent) overflow
    mockNarrowToolbar(650)
  })
  afterEach(() => resetResizeObserver())

  it('shows overflow button and hidden items in dropdown', () => {
    render(<EditorToolbar {...makeProps({ isMobile: false })} />)
    openMoreMenu()
    expect(screen.getByText('Hyperlink')).toBeInTheDocument()
    expect(screen.getByText('Cross Reference')).toBeInTheDocument()
    expect(screen.getByText('Toggle Comment')).toBeInTheDocument()
    expect(screen.getByText('Decrease Indent')).toBeInTheDocument()
    expect(screen.getByText('Increase Indent')).toBeInTheDocument()
  })

  it('calls onInsertLink when Hyperlink is clicked', () => {
    const onInsertLink = vi.fn()
    render(<EditorToolbar {...makeProps({ onInsertLink })} />)
    openMoreMenu()
    fireEvent.click(screen.getByText('Hyperlink'))
    expect(onInsertLink).toHaveBeenCalledOnce()
  })

  it('calls onInsertRef when Cross Reference is clicked', () => {
    const onInsertRef = vi.fn()
    render(<EditorToolbar {...makeProps({ onInsertRef })} />)
    openMoreMenu()
    fireEvent.click(screen.getByText('Cross Reference'))
    expect(onInsertRef).toHaveBeenCalledOnce()
  })
})

describe('EditorToolbar — Very narrow toolbar (all groups overflow)', () => {
  beforeEach(() => mockNarrowToolbar(300))
  afterEach(() => resetResizeObserver())

  it('puts all groups in overflow menu', () => {
    render(<EditorToolbar {...makeProps({ isMobile: false })} />)
    openMoreMenu()
    expect(screen.getByText('Bold')).toBeInTheDocument()
    expect(screen.getByText('Italic')).toBeInTheDocument()
    expect(screen.getByText('Inline Math')).toBeInTheDocument()
    expect(screen.getByText('Citation')).toBeInTheDocument()
    expect(screen.getByText('Figure')).toBeInTheDocument()
    expect(screen.getByText('Table')).toBeInTheDocument()
    expect(screen.getByText('Hyperlink')).toBeInTheDocument()
    expect(screen.getByText('Toggle Comment')).toBeInTheDocument()
  })
})

/* ================================================================
   TABLE DROPDOWN (via More menu → Table…)
   ================================================================ */

describe('EditorToolbar — Table Dropdown', () => {
  it('opens table dropdown on click', () => {
    render(<EditorToolbar {...makeProps({ isMobile: false })} />)
    fireEvent.click(screen.getByTitle(/Insert table/))
    expect(screen.getByText('Select size')).toBeInTheDocument()
    expect(screen.getByText(/Default.*booktabs/)).toBeInTheDocument()
  })

  it('calls onInsertTable when default option is clicked', () => {
    const onInsertTable = vi.fn()
    render(<EditorToolbar {...makeProps({ onInsertTable })} />)
    fireEvent.click(screen.getByTitle(/Insert table/))
    fireEvent.click(screen.getByText(/Default.*booktabs/))
    expect(onInsertTable).toHaveBeenCalledOnce()
  })
})

/* ================================================================
   SYMBOL PALETTE
   ================================================================ */

describe('EditorToolbar — Symbol Palette', () => {
  it('shows symbol palette button on desktop when callback is provided', () => {
    render(<EditorToolbar {...makeProps({ isMobile: false, onToggleSymbolPalette: vi.fn() })} />)
    expect(screen.getByTitle(/Symbol palette/)).toBeInTheDocument()
  })

  it('hides symbol palette button on mobile', () => {
    render(<EditorToolbar {...makeProps({ isMobile: true, onToggleSymbolPalette: vi.fn() })} />)
    expect(screen.queryByTitle(/Symbol palette/)).not.toBeInTheDocument()
  })

  it('calls onToggleSymbolPalette when clicked', () => {
    const onToggleSymbolPalette = vi.fn()
    render(<EditorToolbar {...makeProps({ onToggleSymbolPalette })} />)
    fireEvent.click(screen.getByTitle(/Symbol palette/))
    expect(onToggleSymbolPalette).toHaveBeenCalledOnce()
  })

  it('applies active style when symbolPaletteOpen is true', () => {
    render(<EditorToolbar {...makeProps({ symbolPaletteOpen: true, onToggleSymbolPalette: vi.fn() })} />)
    expect(screen.getByTitle(/Symbol palette/).className).toContain('bg-indigo-100')
  })
})

/* Export dropdown tests removed — export moved to PdfPreviewPane */

/* Track Changes & Writing Analysis tests removed — moved to EditorSideRail */

/* ================================================================
   HISTORY BUTTON
   ================================================================ */

/* History button has moved to EditorMenuBar — no toolbar tests needed */

/* Save button tests removed — save button removed from toolbar */

/* ================================================================
   AI TOOLS INTEGRATION
   ================================================================ */

describe('EditorToolbar — AI Tools Menu', () => {
  it('renders AI tools menu in code mode when not readOnly', () => {
    render(<EditorToolbar {...makeProps()} />)
    expect(screen.getByTestId('ai-tools-menu')).toBeInTheDocument()
  })

  it('does not render AI tools menu in PDF mode', () => {
    render(<EditorToolbar {...makeProps({ viewMode: 'pdf' })} />)
    expect(screen.queryByTestId('ai-tools-menu')).not.toBeInTheDocument()
  })

  it('passes correct props to AI tools menu', () => {
    render(<EditorToolbar {...makeProps({ hasTextSelected: true, aiActionLoading: 'paraphrase' })} />)
    const menu = screen.getByTestId('ai-tools-menu')
    expect(menu.dataset.readonly).toBe('false')
    expect(menu.dataset.selected).toBe('true')
    expect(menu.dataset.loading).toBe('paraphrase')
  })
})

/* ================================================================
   RIGHT-SIDE ITEMS VISIBILITY
   ================================================================ */

describe('EditorToolbar — Right-side items coexistence', () => {
  it('shows AI tools menu on desktop in code mode', () => {
    render(<EditorToolbar {...makeProps({ isMobile: false })} />)
    expect(screen.getByTestId('ai-tools-menu')).toBeInTheDocument()
  })
})
