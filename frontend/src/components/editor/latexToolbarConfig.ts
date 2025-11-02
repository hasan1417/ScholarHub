import type { LucideIcon } from 'lucide-react'
import {
  Heading1,
  Heading2,
  Pilcrow,
  BoldIcon,
  ItalicIcon,
  Type,
  CodeIcon,
  Quote,
  Footprints,
  Sigma,
  FunctionSquare,
  Brackets,
  List,
  ListOrdered,
  ListChecks,
  Image,
  TableIcon,
  BookOpen,
  Quote as QuoteIcon,
} from 'lucide-react'

export interface LatexToolbarItemConfig {
  key: string
  label: string
  title: string
  Icon: LucideIcon
}

export interface LatexToolbarGroupConfig {
  label: string
  items: LatexToolbarItemConfig[]
}

export const LATEX_FORMATTING_GROUPS: LatexToolbarGroupConfig[] = [
  {
    label: 'Structure',
    items: [
      { key: 'section', label: 'Section', title: 'Insert \\section heading', Icon: Heading1 },
      { key: 'subsection', label: 'Subsection', title: 'Insert \\subsection heading', Icon: Heading2 },
      { key: 'paragraph', label: 'Paragraph', title: 'Insert \\paragraph heading', Icon: Pilcrow },
    ],
  },
  {
    label: 'Text',
    items: [
      { key: 'bold', label: 'Bold', title: 'Wrap selection in \\textbf{…}', Icon: BoldIcon },
      { key: 'italic', label: 'Italic', title: 'Wrap selection in \\textit{…}', Icon: ItalicIcon },
      { key: 'smallcaps', label: 'Small Caps', title: 'Wrap selection in \\textsc{…}', Icon: Type },
      { key: 'code', label: 'Code', title: 'Wrap selection in \\texttt{…}', Icon: CodeIcon },
      { key: 'quote', label: 'Quote', title: 'Insert quote environment', Icon: Quote },
      { key: 'footnote', label: 'Footnote', title: 'Insert \\footnote{}', Icon: Footprints },
    ],
  },
  {
    label: 'Math',
    items: [
      { key: 'math-inline', label: 'Inline Math', title: 'Insert inline $…$ math', Icon: Sigma },
      { key: 'math-display', label: 'Display Math', title: 'Insert display math block', Icon: FunctionSquare },
      { key: 'align', label: 'Align Block', title: 'Insert align environment', Icon: Brackets },
    ],
  },
  {
    label: 'Lists',
    items: [
      { key: 'itemize', label: 'Bullet List', title: 'Insert itemize environment', Icon: List },
      { key: 'enumerate', label: 'Numbered List', title: 'Insert enumerate environment', Icon: ListOrdered },
      { key: 'description', label: 'Description', title: 'Insert description environment', Icon: ListChecks },
    ],
  },
  {
    label: 'Floats',
    items: [
      { key: 'figure', label: 'Figure', title: 'Insert figure environment', Icon: Image },
      { key: 'table', label: 'Table', title: 'Insert table environment', Icon: TableIcon },
    ],
  },
  {
    label: 'References',
    items: [
      { key: 'cite', label: 'Citation', title: 'Insert \\cite{} command', Icon: QuoteIcon },
      { key: 'bibliography', label: 'Bibliography', title: 'Insert bibliography commands', Icon: BookOpen },
    ],
  },
]
