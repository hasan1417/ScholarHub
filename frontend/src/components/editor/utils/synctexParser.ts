/**
 * Minimal SyncTeX parser — replaces the buggy `synctex-js` npm package
 * which uses undeclared `match` variable (crashes in ESM strict mode).
 *
 * Based on the same synctex format but with proper TypeScript types.
 */

export interface SyncTeXElement {
  type: string
  fileNumber: number
  file: { path: string; name: string }
  line: number
  left: number
  bottom: number
  height: number
  width: number | null
  page: number
  parent?: SyncTeXElement
}

export interface SyncTeXPage {
  page: number
  blocks: SyncTeXElement[]
  type: string
}

export interface SyncTeXData {
  blockNumberLine: Record<string, Record<number, Record<number, SyncTeXElement[]>>>
  hBlocks: SyncTeXElement[]
  pages: Record<string, SyncTeXPage>
  files: Record<string, { path: string; name: string }>
  numberPages: number
  offset: { x: number; y: number }
}

const UNIT = 65781.76

export function parseSyncTex(body: string): SyncTeXData {
  const result: SyncTeXData = {
    offset: { x: 0, y: 0 },
    files: {},
    pages: {},
    blockNumberLine: {},
    hBlocks: [],
    numberPages: 0,
  }

  if (!body) return result

  const lines = body.split('\n')

  const inputPat = /Input:([0-9]+):(.+)/
  const offsetPat = /(X|Y) Offset:([0-9]+)/
  const openPagePat = /\{([0-9]+)$/
  const closePagePat = /\}([0-9]+)$/
  const vBlockPat = /\[([0-9]+),([0-9]+):(-?[0-9]+),(-?[0-9]+):(-?[0-9]+),(-?[0-9]+),(-?[0-9]+)/
  const closeVPat = /\]$/
  const hBlockPat = /\(([0-9]+),([0-9]+):(-?[0-9]+),(-?[0-9]+):(-?[0-9]+),(-?[0-9]+),(-?[0-9]+)/
  const closeHPat = /\)$/
  const elemPat = /(.)([0-9]+),([0-9]+):-?([0-9]+),-?([0-9]+)(:?-?([0-9]+))?/

  let numberPages = 0
  let currentPage: any = null
  let currentElement: any = null
  const files: Record<string, { path: string; name: string }> = {}
  const pages: Record<string, SyncTeXPage> = {}
  const blockNumberLine: Record<string, Record<number, Record<number, SyncTeXElement[]>>> = {}
  const hBlocks: SyncTeXElement[] = []

  for (let i = 1; i < lines.length; i++) {
    const line = lines[i]
    let m: RegExpMatchArray | null

    // Input files
    m = line.match(inputPat)
    if (m) {
      files[m[1]] = { path: m[2], name: m[2].replace(/^.*[/\\]/, '') }
      continue
    }

    // Offset
    m = line.match(offsetPat)
    if (m) {
      (result.offset as any)[m[1].toLowerCase()] = parseInt(m[2]) / UNIT
      continue
    }

    // Open page
    m = line.match(openPagePat)
    if (m) {
      currentPage = { page: parseInt(m[1]), blocks: [], type: 'page' }
      if (currentPage.page > numberPages) numberPages = currentPage.page
      currentElement = currentPage
      continue
    }

    // Close page
    m = line.match(closePagePat)
    if (m) {
      if (currentPage) pages[m[1]] = currentPage
      currentPage = null
      continue
    }

    // Vertical block
    m = line.match(vBlockPat)
    if (m) {
      const block: any = {
        type: 'vertical',
        parent: currentElement,
        fileNumber: parseInt(m[1]),
        file: files[m[1]],
        line: parseInt(m[2]),
        left: parseInt(m[3]) / UNIT,
        bottom: parseInt(m[4]) / UNIT,
        width: parseInt(m[5]) / UNIT,
        height: parseInt(m[6]) / UNIT,
        depth: parseInt(m[7]),
        blocks: [],
        elements: [],
        page: currentPage?.page ?? 0,
      }
      currentElement = block
      continue
    }

    // Close V block
    m = line.match(closeVPat)
    if (m) {
      if (currentElement?.parent) {
        currentElement.parent.blocks?.push(currentElement)
        currentElement = currentElement.parent
      }
      continue
    }

    // Horizontal block
    m = line.match(hBlockPat)
    if (m) {
      const block: any = {
        type: 'horizontal',
        parent: currentElement,
        fileNumber: parseInt(m[1]),
        file: files[m[1]],
        line: parseInt(m[2]),
        left: parseInt(m[3]) / UNIT,
        bottom: parseInt(m[4]) / UNIT,
        width: parseInt(m[5]) / UNIT,
        height: parseInt(m[6]) / UNIT,
        blocks: [],
        elements: [],
        page: currentPage?.page ?? 0,
      }
      hBlocks.push(block)
      currentElement = block
      continue
    }

    // Close H block
    m = line.match(closeHPat)
    if (m) {
      if (currentElement?.parent) {
        currentElement.parent.blocks?.push(currentElement)
        currentElement = currentElement.parent
      }
      continue
    }

    // Element
    m = line.match(elemPat)
    if (m) {
      const fileNumber = parseInt(m[2])
      const lineNumber = parseInt(m[3])
      const elem: SyncTeXElement = {
        type: m[1],
        fileNumber,
        file: files[fileNumber] || { path: '', name: 'main.tex' },
        line: lineNumber,
        left: parseInt(m[4]) / UNIT,
        bottom: parseInt(m[5]) / UNIT,
        height: currentElement?.height ?? 0,
        width: m[7] ? parseInt(m[7]) / UNIT : null,
        page: currentPage?.page ?? 0,
      }

      const fileName = elem.file.name
      if (!blockNumberLine[fileName]) blockNumberLine[fileName] = {}
      if (!blockNumberLine[fileName][lineNumber]) blockNumberLine[fileName][lineNumber] = {}
      if (!blockNumberLine[fileName][lineNumber][elem.page]) blockNumberLine[fileName][lineNumber][elem.page] = []
      blockNumberLine[fileName][lineNumber][elem.page].push(elem)

      if (currentElement?.elements) currentElement.elements.push(elem)
      continue
    }
  }

  result.files = files
  result.pages = pages
  result.blockNumberLine = blockNumberLine
  result.hBlocks = hBlocks
  result.numberPages = numberPages
  return result
}
