import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, act } from '@testing-library/react'
import { SectionHeadingDropdown } from '../components/editor/components/SectionHeadingDropdown'
import { EditorState } from '@codemirror/state'
import { EditorView } from '@codemirror/view'

// Helper: create a real CodeMirror EditorView with given doc content and cursor position
function createMockView(doc: string, cursorPos?: number): EditorView {
  const state = EditorState.create({
    doc,
    selection: { anchor: cursorPos ?? 0 },
  })
  // Create a real EditorView attached to a detached div
  const container = document.createElement('div')
  return new EditorView({ state, parent: container })
}

function makeRef(view: EditorView | null = null) {
  return { current: view } as React.RefObject<EditorView | null>
}

// Suppress timers so polling doesn't cause act() warnings
beforeEach(() => {
  vi.useFakeTimers()
})
afterEach(() => {
  vi.useRealTimers()
})

/* ================================================================
   RENDERING
   ================================================================ */

describe('SectionHeadingDropdown — Rendering', () => {
  it('renders with "Normal text" label by default (no editor)', () => {
    render(<SectionHeadingDropdown editorViewRef={makeRef()} />)
    expect(screen.getByText('Normal text')).toBeInTheDocument()
  })

  it('renders with "Normal text" when cursor is on a plain line', () => {
    const view = createMockView('Hello world', 3)
    render(<SectionHeadingDropdown editorViewRef={makeRef(view)} />)
    act(() => { vi.advanceTimersByTime(300) })
    expect(screen.getByText('Normal text')).toBeInTheDocument()
  })

  it('detects \\section heading at cursor', () => {
    const doc = '\\section{Introduction}'
    const view = createMockView(doc, 5)
    render(<SectionHeadingDropdown editorViewRef={makeRef(view)} />)
    act(() => { vi.advanceTimersByTime(300) })
    expect(screen.getByText('Section')).toBeInTheDocument()
  })

  it('detects \\subsection heading at cursor', () => {
    const doc = '\\subsection{Background}'
    const view = createMockView(doc, 5)
    render(<SectionHeadingDropdown editorViewRef={makeRef(view)} />)
    act(() => { vi.advanceTimersByTime(300) })
    expect(screen.getByText('Subsection')).toBeInTheDocument()
  })

  it('detects \\subsubsection heading at cursor', () => {
    const doc = '\\subsubsection{Details}'
    const view = createMockView(doc, 5)
    render(<SectionHeadingDropdown editorViewRef={makeRef(view)} />)
    act(() => { vi.advanceTimersByTime(300) })
    expect(screen.getByText('Subsubsection')).toBeInTheDocument()
  })
})

/* ================================================================
   DROPDOWN OPEN / CLOSE
   ================================================================ */

describe('SectionHeadingDropdown — Dropdown Toggle', () => {
  it('opens dropdown on click and shows all heading options', () => {
    render(<SectionHeadingDropdown editorViewRef={makeRef()} />)
    fireEvent.click(screen.getByText('Normal text'))
    expect(screen.getByText('Section')).toBeInTheDocument()
    expect(screen.getByText('Subsection')).toBeInTheDocument()
    expect(screen.getByText('Subsubsection')).toBeInTheDocument()
    expect(screen.getByText('Paragraph')).toBeInTheDocument()
    expect(screen.getByText('Subparagraph')).toBeInTheDocument()
    // "Normal text" appears both as current label and in dropdown
    expect(screen.getAllByText('Normal text').length).toBeGreaterThanOrEqual(2)
  })

  it('closes dropdown when clicking backdrop', () => {
    render(<SectionHeadingDropdown editorViewRef={makeRef()} />)
    fireEvent.click(screen.getByText('Normal text'))
    expect(screen.getByText('Section')).toBeInTheDocument()
    // The fixed backdrop is the first child of the fragment when open
    const backdrop = document.querySelector('.fixed.inset-0.z-40')
    expect(backdrop).not.toBeNull()
    fireEvent.click(backdrop!)
    // After closing, dropdown options should be gone
    // "Section" only appears in the dropdown, not in the label
    expect(screen.queryAllByText('Section').length).toBeLessThanOrEqual(0)
  })

  it('toggles dropdown on repeated clicks', () => {
    render(<SectionHeadingDropdown editorViewRef={makeRef()} />)
    const trigger = screen.getByText('Normal text')
    fireEvent.click(trigger)
    expect(screen.getByText('Section')).toBeInTheDocument()
    fireEvent.click(trigger)
    expect(screen.queryByText('Section')).not.toBeInTheDocument()
  })
})

/* ================================================================
   HEADING INSERTION (Normal text → heading)
   ================================================================ */

describe('SectionHeadingDropdown — Inserting Headings', () => {
  it('wraps normal text line with \\section{} when Section is selected', () => {
    const doc = 'Introduction'
    const view = createMockView(doc, 5)
    render(<SectionHeadingDropdown editorViewRef={makeRef(view)} />)
    act(() => { vi.advanceTimersByTime(300) })

    fireEvent.click(screen.getByText('Normal text')) // open dropdown
    fireEvent.click(screen.getAllByText('Section')[0]) // select Section (use first match in dropdown)

    const result = view.state.doc.toString()
    expect(result).toBe('\\section{Introduction}')
  })

  it('wraps normal text with \\subsection{} when Subsection is selected', () => {
    const doc = 'Background'
    const view = createMockView(doc, 3)
    render(<SectionHeadingDropdown editorViewRef={makeRef(view)} />)
    act(() => { vi.advanceTimersByTime(300) })

    fireEvent.click(screen.getByText('Normal text'))
    fireEvent.click(screen.getByText('Subsection'))

    expect(view.state.doc.toString()).toBe('\\subsection{Background}')
  })

  it('does nothing when selecting "Normal text" on normal text', () => {
    const doc = 'Just text'
    const view = createMockView(doc, 3)
    render(<SectionHeadingDropdown editorViewRef={makeRef(view)} />)
    act(() => { vi.advanceTimersByTime(300) })

    fireEvent.click(screen.getByText('Normal text')) // open dropdown
    // Click the "Normal text" option inside the dropdown
    const options = screen.getAllByText('Normal text')
    fireEvent.click(options[options.length - 1]) // last one is in the dropdown

    expect(view.state.doc.toString()).toBe('Just text')
  })
})

/* ================================================================
   HEADING REPLACEMENT (heading → different heading)
   ================================================================ */

describe('SectionHeadingDropdown — Replacing Headings', () => {
  it('replaces \\section with \\subsection', () => {
    const doc = '\\section{Introduction}'
    const view = createMockView(doc, 5)
    render(<SectionHeadingDropdown editorViewRef={makeRef(view)} />)
    act(() => { vi.advanceTimersByTime(300) })

    fireEvent.click(screen.getByText('Section')) // open dropdown (label shows "Section")
    fireEvent.click(screen.getByText('Subsection'))

    expect(view.state.doc.toString()).toBe('\\subsection{Introduction}')
  })

  it('replaces \\subsection with \\section', () => {
    const doc = '\\subsection{Background}'
    const view = createMockView(doc, 5)
    render(<SectionHeadingDropdown editorViewRef={makeRef(view)} />)
    act(() => { vi.advanceTimersByTime(300) })

    fireEvent.click(screen.getByText('Subsection'))
    // Find the Section option in the dropdown
    const options = screen.getAllByText('Section')
    fireEvent.click(options[0])

    expect(view.state.doc.toString()).toBe('\\section{Background}')
  })
})

/* ================================================================
   HEADING REMOVAL (heading → normal text)
   ================================================================ */

describe('SectionHeadingDropdown — Removing Headings', () => {
  it('converts \\section{Title} to just "Title" when Normal text is selected', () => {
    const doc = '\\section{Introduction}'
    const view = createMockView(doc, 5)
    render(<SectionHeadingDropdown editorViewRef={makeRef(view)} />)
    act(() => { vi.advanceTimersByTime(300) })

    fireEvent.click(screen.getByText('Section')) // open dropdown
    // Click "Normal text" in the dropdown
    const options = screen.getAllByText('Normal text')
    fireEvent.click(options[0])

    expect(view.state.doc.toString()).toBe('Introduction')
  })

  it('converts \\subsection{Background} to "Background"', () => {
    const doc = '\\subsection{Background}'
    const view = createMockView(doc, 5)
    render(<SectionHeadingDropdown editorViewRef={makeRef(view)} />)
    act(() => { vi.advanceTimersByTime(300) })

    fireEvent.click(screen.getByText('Subsection'))
    const options = screen.getAllByText('Normal text')
    fireEvent.click(options[0])

    expect(view.state.doc.toString()).toBe('Background')
  })
})

/* ================================================================
   MULTI-LINE DOCUMENT
   ================================================================ */

describe('SectionHeadingDropdown — Multi-line', () => {
  it('only modifies the line where the cursor is', () => {
    const doc = '\\section{First}\nSome body text\n\\section{Second}'
    // Place cursor on line 2 ("Some body text"), position is after first \n
    const cursorPos = doc.indexOf('Some') + 2
    const view = createMockView(doc, cursorPos)
    render(<SectionHeadingDropdown editorViewRef={makeRef(view)} />)
    act(() => { vi.advanceTimersByTime(300) })

    // Label should say "Normal text" since cursor is on a non-heading line
    fireEvent.click(screen.getByText('Normal text'))
    fireEvent.click(screen.getAllByText('Subsection')[0])

    const result = view.state.doc.toString()
    expect(result).toBe('\\section{First}\n\\subsection{Some body text}\n\\section{Second}')
  })
})
