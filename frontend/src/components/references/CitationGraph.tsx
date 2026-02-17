import { useCallback, useEffect, useRef, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Loader2, ZoomIn, ZoomOut, Maximize2 } from 'lucide-react'
import { projectReferencesAPI } from '../../services/api'
import type { CitationGraphNode, CitationGraphEdge } from '../../types'

// ---------------------------------------------------------------------------
// Force simulation types
// ---------------------------------------------------------------------------

interface SimNode extends CitationGraphNode {
  x: number
  y: number
  vx: number
  vy: number
  fx: number | null
  fy: number | null
}

interface Props {
  projectId: string
}

// ---------------------------------------------------------------------------
// Colors
// ---------------------------------------------------------------------------

const NODE_COLORS: Record<string, { fill: string; stroke: string; darkFill: string; darkStroke: string }> = {
  library: { fill: '#6366f1', stroke: '#4f46e5', darkFill: '#818cf8', darkStroke: '#6366f1' },
  cited: { fill: '#94a3b8', stroke: '#64748b', darkFill: '#94a3b8', darkStroke: '#64748b' },
  citing: { fill: '#10b981', stroke: '#059669', darkFill: '#34d399', darkStroke: '#10b981' },
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function truncate(text: string, max: number): string {
  if (text.length <= max) return text
  return text.slice(0, max - 1) + '\u2026'
}

function isDarkMode(): boolean {
  if (typeof document === 'undefined') return false
  return document.documentElement.classList.contains('dark')
}

// ---------------------------------------------------------------------------
// Force simulation
// ---------------------------------------------------------------------------

function initializePositions(nodes: SimNode[], width: number, height: number) {
  const cx = width / 2
  const cy = height / 2
  for (let i = 0; i < nodes.length; i++) {
    const angle = (2 * Math.PI * i) / nodes.length
    const radius = Math.min(width, height) * 0.3
    nodes[i].x = cx + radius * Math.cos(angle) + (Math.random() - 0.5) * 20
    nodes[i].y = cy + radius * Math.sin(angle) + (Math.random() - 0.5) * 20
    nodes[i].vx = 0
    nodes[i].vy = 0
    nodes[i].fx = null
    nodes[i].fy = null
  }
}

function simulate(
  nodes: SimNode[],
  edges: CitationGraphEdge[],
  width: number,
  height: number,
  alpha: number,
): number {
  const cx = width / 2
  const cy = height / 2
  const damping = 0.6
  const repulsionStrength = 1200
  const attractionStrength = 0.006
  const centerStrength = 0.01

  // Repulsion between all nodes
  for (let i = 0; i < nodes.length; i++) {
    for (let j = i + 1; j < nodes.length; j++) {
      let dx = nodes[j].x - nodes[i].x
      let dy = nodes[j].y - nodes[i].y
      let dist = Math.sqrt(dx * dx + dy * dy) || 1
      if (dist < 1) dist = 1
      const force = (repulsionStrength * alpha) / (dist * dist)
      const fx = (dx / dist) * force
      const fy = (dy / dist) * force
      nodes[i].vx -= fx
      nodes[i].vy -= fy
      nodes[j].vx += fx
      nodes[j].vy += fy
    }
  }

  // Build node index for edge lookup
  const nodeMap = new Map<string, number>()
  for (let i = 0; i < nodes.length; i++) {
    nodeMap.set(nodes[i].id, i)
  }

  // Attraction along edges
  for (const edge of edges) {
    const si = nodeMap.get(edge.source)
    const ti = nodeMap.get(edge.target)
    if (si === undefined || ti === undefined) continue
    const dx = nodes[ti].x - nodes[si].x
    const dy = nodes[ti].y - nodes[si].y
    const dist = Math.sqrt(dx * dx + dy * dy) || 1
    const idealDist = 120
    const force = (dist - idealDist) * attractionStrength * alpha
    const fx = (dx / dist) * force
    const fy = (dy / dist) * force
    nodes[si].vx += fx
    nodes[si].vy += fy
    nodes[ti].vx -= fx
    nodes[ti].vy -= fy
  }

  // Center gravity
  for (const node of nodes) {
    node.vx += (cx - node.x) * centerStrength * alpha
    node.vy += (cy - node.y) * centerStrength * alpha
  }

  // Apply velocity
  for (const node of nodes) {
    if (node.fx !== null) {
      node.x = node.fx
      node.vx = 0
    } else {
      node.vx *= damping
      node.x += node.vx
    }
    if (node.fy !== null) {
      node.y = node.fy
      node.vy = 0
    } else {
      node.vy *= damping
      node.y += node.vy
    }
  }

  return alpha * 0.99
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

const CitationGraph: React.FC<Props> = ({ projectId }) => {
  const svgRef = useRef<SVGSVGElement>(null)
  const containerRef = useRef<HTMLDivElement>(null)
  const nodesRef = useRef<SimNode[]>([])
  const edgesRef = useRef<CitationGraphEdge[]>([])
  const animFrameRef = useRef<number>(0)
  const alphaRef = useRef(1)
  const tickRef = useRef(0)

  const [, setRenderTick] = useState(0) // force re-render
  const [dimensions, setDimensions] = useState({ width: 800, height: 500 })
  const [tooltip, setTooltip] = useState<{ x: number; y: number; node: SimNode } | null>(null)
  const [dragging, setDragging] = useState<SimNode | null>(null)
  const [transform, setTransform] = useState({ x: 0, y: 0, k: 1 })
  const [panning, setPanning] = useState(false)
  const panStartRef = useRef({ x: 0, y: 0, tx: 0, ty: 0 })

  const { data, isLoading, error } = useQuery({
    queryKey: ['project', projectId, 'citationGraph'],
    queryFn: async () => {
      const resp = await projectReferencesAPI.getCitationGraph(projectId)
      return resp.data
    },
  })

  // Measure container
  useEffect(() => {
    const measure = () => {
      if (containerRef.current) {
        const rect = containerRef.current.getBoundingClientRect()
        setDimensions({ width: rect.width || 800, height: Math.max(rect.height, 500) })
      }
    }
    measure()
    window.addEventListener('resize', measure)
    return () => window.removeEventListener('resize', measure)
  }, [])

  // Initialize simulation when data changes
  useEffect(() => {
    if (!data || data.nodes.length === 0) return

    const simNodes: SimNode[] = data.nodes.map((n) => ({
      ...n,
      x: 0,
      y: 0,
      vx: 0,
      vy: 0,
      fx: null,
      fy: null,
    }))

    initializePositions(simNodes, dimensions.width, dimensions.height)
    nodesRef.current = simNodes
    edgesRef.current = data.edges
    alphaRef.current = 1
    tickRef.current = 0

    const run = () => {
      if (tickRef.current > 300 && alphaRef.current < 0.01) {
        return
      }
      alphaRef.current = simulate(
        nodesRef.current,
        edgesRef.current,
        dimensions.width,
        dimensions.height,
        alphaRef.current,
      )
      tickRef.current++
      setRenderTick((t) => t + 1)
      animFrameRef.current = requestAnimationFrame(run)
    }

    animFrameRef.current = requestAnimationFrame(run)

    return () => {
      if (animFrameRef.current) cancelAnimationFrame(animFrameRef.current)
    }
  }, [data, dimensions.width, dimensions.height])

  // Drag handlers
  const handleMouseDown = useCallback(
    (node: SimNode, e: React.MouseEvent) => {
      e.stopPropagation()
      e.preventDefault()
      setDragging(node)
      node.fx = node.x
      node.fy = node.y
      // Reheat simulation
      alphaRef.current = 0.3
      tickRef.current = 0
      const run = () => {
        if (tickRef.current > 300 && alphaRef.current < 0.01) return
        alphaRef.current = simulate(
          nodesRef.current,
          edgesRef.current,
          dimensions.width,
          dimensions.height,
          alphaRef.current,
        )
        tickRef.current++
        setRenderTick((t) => t + 1)
        animFrameRef.current = requestAnimationFrame(run)
      }
      if (animFrameRef.current) cancelAnimationFrame(animFrameRef.current)
      animFrameRef.current = requestAnimationFrame(run)
    },
    [dimensions],
  )

  const handleMouseMove = useCallback(
    (e: React.MouseEvent) => {
      if (dragging) {
        const svg = svgRef.current
        if (!svg) return
        const rect = svg.getBoundingClientRect()
        const x = (e.clientX - rect.left - transform.x) / transform.k
        const y = (e.clientY - rect.top - transform.y) / transform.k
        dragging.fx = x
        dragging.fy = y
        dragging.x = x
        dragging.y = y
        setRenderTick((t) => t + 1)
      } else if (panning) {
        const dx = e.clientX - panStartRef.current.x
        const dy = e.clientY - panStartRef.current.y
        setTransform((prev) => ({
          ...prev,
          x: panStartRef.current.tx + dx,
          y: panStartRef.current.ty + dy,
        }))
      }
    },
    [dragging, panning, transform.x, transform.y, transform.k],
  )

  const handleMouseUp = useCallback(() => {
    if (dragging) {
      dragging.fx = null
      dragging.fy = null
      setDragging(null)
    }
    if (panning) {
      setPanning(false)
    }
  }, [dragging, panning])

  const handleSvgMouseDown = useCallback(
    (e: React.MouseEvent) => {
      if (dragging) return
      // Only pan on left-click on SVG background
      if (e.button !== 0) return
      setPanning(true)
      panStartRef.current = { x: e.clientX, y: e.clientY, tx: transform.x, ty: transform.y }
    },
    [dragging, transform.x, transform.y],
  )

  const handleWheel = useCallback((e: React.WheelEvent) => {
    e.preventDefault()
    const scaleFactor = e.deltaY > 0 ? 0.9 : 1.1
    setTransform((prev) => {
      const newK = Math.min(Math.max(prev.k * scaleFactor, 0.2), 4)
      // Zoom toward cursor
      const svg = svgRef.current
      if (!svg) return { ...prev, k: newK }
      const rect = svg.getBoundingClientRect()
      const mx = e.clientX - rect.left
      const my = e.clientY - rect.top
      return {
        k: newK,
        x: mx - ((mx - prev.x) / prev.k) * newK,
        y: my - ((my - prev.y) / prev.k) * newK,
      }
    })
  }, [])

  const handleNodeClick = useCallback(
    (node: SimNode) => {
      if (node.in_library) {
        // Already in library -- no extra navigation for now, could be extended
      } else if (node.doi) {
        window.open(`https://doi.org/${node.doi}`, '_blank', 'noopener')
      }
    },
    [],
  )

  const zoomIn = () =>
    setTransform((prev) => ({ ...prev, k: Math.min(prev.k * 1.3, 4) }))
  const zoomOut = () =>
    setTransform((prev) => ({ ...prev, k: Math.max(prev.k / 1.3, 0.2) }))
  const resetView = () => setTransform({ x: 0, y: 0, k: 1 })

  // Build edge lookup for node id
  const nodeMap = new Map<string, SimNode>()
  for (const n of nodesRef.current) nodeMap.set(n.id, n)

  const dark = isDarkMode()

  if (isLoading) {
    return (
      <div className="flex items-center justify-center gap-3 rounded-2xl border border-gray-200 bg-white p-12 text-sm text-gray-600 dark:border-slate-700 dark:bg-slate-900/60 dark:text-slate-300">
        <Loader2 className="h-5 w-5 animate-spin text-indigo-600 dark:text-indigo-300" />
        Building citation graph...
      </div>
    )
  }

  if (error) {
    return (
      <div className="rounded-2xl border border-dashed border-gray-300 bg-gray-50 p-8 text-center text-sm text-gray-500 dark:border-slate-700 dark:bg-slate-900/60 dark:text-slate-400">
        Failed to load citation graph. Please try again later.
      </div>
    )
  }

  if (!data || data.nodes.length === 0) {
    return (
      <div className="rounded-2xl border border-dashed border-gray-300 bg-gray-50 p-8 text-center text-sm text-gray-500 dark:border-slate-700 dark:bg-slate-900/60 dark:text-slate-400">
        <p className="font-medium text-gray-700 dark:text-slate-200">No citation data available</p>
        <p className="mt-1">Add papers with DOIs to your library to see how they cite each other.</p>
      </div>
    )
  }

  const arrowId = 'citation-arrow'
  const arrowIdDark = 'citation-arrow-dark'

  return (
    <div className="space-y-3">
      {/* Legend and controls */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-4 text-xs text-gray-500 dark:text-slate-400">
          <span className="flex items-center gap-1.5">
            <span className="inline-block h-3 w-3 rounded-full" style={{ background: NODE_COLORS.library.fill }} />
            In your library
          </span>
          <span className="flex items-center gap-1.5">
            <span className="inline-block h-3 w-3 rounded-full" style={{ background: NODE_COLORS.cited.fill }} />
            Older work they referenced
          </span>
          <span className="flex items-center gap-1.5">
            <span className="inline-block h-3 w-3 rounded-full" style={{ background: NODE_COLORS.citing.fill }} />
            Newer work that cites them
          </span>
          <span className="flex items-center gap-1.5 text-gray-400 dark:text-slate-500">
            <svg width="20" height="10"><line x1="0" y1="5" x2="14" y2="5" stroke="currentColor" strokeWidth="1.5" /><polygon points="14,2 20,5 14,8" fill="currentColor" /></svg>
            Cites
          </span>
        </div>
        <div className="flex items-center gap-1">
          <button
            onClick={zoomIn}
            className="rounded-lg p-1.5 text-gray-400 hover:bg-gray-100 hover:text-gray-600 dark:text-slate-500 dark:hover:bg-slate-800 dark:hover:text-slate-300"
            title="Zoom in"
          >
            <ZoomIn className="h-4 w-4" />
          </button>
          <button
            onClick={zoomOut}
            className="rounded-lg p-1.5 text-gray-400 hover:bg-gray-100 hover:text-gray-600 dark:text-slate-500 dark:hover:bg-slate-800 dark:hover:text-slate-300"
            title="Zoom out"
          >
            <ZoomOut className="h-4 w-4" />
          </button>
          <button
            onClick={resetView}
            className="rounded-lg p-1.5 text-gray-400 hover:bg-gray-100 hover:text-gray-600 dark:text-slate-500 dark:hover:bg-slate-800 dark:hover:text-slate-300"
            title="Reset view"
          >
            <Maximize2 className="h-4 w-4" />
          </button>
        </div>
      </div>

      {/* Graph */}
      <div
        ref={containerRef}
        className="relative overflow-hidden rounded-2xl border border-gray-200 bg-white dark:border-slate-700 dark:bg-slate-900/50"
        style={{ height: 500 }}
      >
        <svg
          ref={svgRef}
          width={dimensions.width}
          height={500}
          className="cursor-grab active:cursor-grabbing"
          onMouseDown={handleSvgMouseDown}
          onMouseMove={handleMouseMove}
          onMouseUp={handleMouseUp}
          onMouseLeave={handleMouseUp}
          onWheel={handleWheel}
          style={{ userSelect: 'none' }}
        >
          <defs>
            <marker
              id={arrowId}
              viewBox="0 0 10 6"
              refX="10"
              refY="3"
              markerWidth="8"
              markerHeight="6"
              orient="auto-start-reverse"
            >
              <path d="M 0 0 L 10 3 L 0 6 z" fill="#cbd5e1" />
            </marker>
            <marker
              id={arrowIdDark}
              viewBox="0 0 10 6"
              refX="10"
              refY="3"
              markerWidth="8"
              markerHeight="6"
              orient="auto-start-reverse"
            >
              <path d="M 0 0 L 10 3 L 0 6 z" fill="#475569" />
            </marker>
          </defs>

          <g transform={`translate(${transform.x},${transform.y}) scale(${transform.k})`}>
            {/* Edges */}
            {edgesRef.current.map((edge, i) => {
              const source = nodeMap.get(edge.source)
              const target = nodeMap.get(edge.target)
              if (!source || !target) return null

              // Shorten line to stop at node edge
              const dx = target.x - source.x
              const dy = target.y - source.y
              const dist = Math.sqrt(dx * dx + dy * dy) || 1
              const sourceR = source.in_library ? 10 : 7
              const targetR = target.in_library ? 10 : 7
              const x1 = source.x + (dx / dist) * sourceR
              const y1 = source.y + (dy / dist) * sourceR
              const x2 = target.x - (dx / dist) * (targetR + 8) // offset for arrowhead
              const y2 = target.y - (dy / dist) * (targetR + 8)

              return (
                <line
                  key={`edge-${i}`}
                  x1={x1}
                  y1={y1}
                  x2={x2}
                  y2={y2}
                  stroke={dark ? '#475569' : '#cbd5e1'}
                  strokeWidth={1}
                  markerEnd={`url(#${dark ? arrowIdDark : arrowId})`}
                  opacity={0.7}
                />
              )
            })}

            {/* Nodes */}
            {nodesRef.current.map((node) => {
              const colors = NODE_COLORS[node.type] || NODE_COLORS.cited
              const r = node.in_library ? 10 : 7
              const fill = dark ? colors.darkFill : colors.fill
              const stroke = dark ? colors.darkStroke : colors.stroke

              return (
                <g
                  key={node.id}
                  style={{ cursor: 'pointer' }}
                  onMouseDown={(e) => handleMouseDown(node, e)}
                  onMouseEnter={(e) => {
                    const rect = svgRef.current?.getBoundingClientRect()
                    if (rect) {
                      setTooltip({
                        x: e.clientX - rect.left,
                        y: e.clientY - rect.top - 10,
                        node,
                      })
                    }
                  }}
                  onMouseLeave={() => setTooltip(null)}
                  onClick={() => handleNodeClick(node)}
                >
                  {/* Glow for library nodes */}
                  {node.in_library && (
                    <circle cx={node.x} cy={node.y} r={r + 4} fill={fill} opacity={0.15} />
                  )}
                  <circle
                    cx={node.x}
                    cy={node.y}
                    r={r}
                    fill={fill}
                    stroke={stroke}
                    strokeWidth={1.5}
                  />
                  {/* Label */}
                  <text
                    x={node.x}
                    y={node.y + r + 12}
                    textAnchor="middle"
                    fontSize={node.in_library ? 9 : 8}
                    fontWeight={node.in_library ? 600 : 400}
                    fill={dark ? '#cbd5e1' : '#475569'}
                    style={{ pointerEvents: 'none' }}
                  >
                    {truncate(node.title, 25)}
                  </text>
                </g>
              )
            })}
          </g>
        </svg>

        {/* Tooltip */}
        {tooltip && (
          <div
            className="pointer-events-none absolute z-50 max-w-xs rounded-lg border border-gray-200 bg-white px-3 py-2 text-xs shadow-lg dark:border-slate-600 dark:bg-slate-800"
            style={{
              left: tooltip.x,
              top: tooltip.y,
              transform: 'translate(-50%, -100%)',
            }}
          >
            <p className="font-semibold text-gray-900 dark:text-slate-100">{tooltip.node.title}</p>
            {tooltip.node.authors.length > 0 && (
              <p className="mt-0.5 text-gray-500 dark:text-slate-400">
                {tooltip.node.authors.join(', ')}
              </p>
            )}
            <div className="mt-1 flex items-center gap-2 text-gray-400 dark:text-slate-500">
              {tooltip.node.year && <span>{tooltip.node.year}</span>}
              {tooltip.node.doi && <span>DOI: {tooltip.node.doi}</span>}
              <span
                className="rounded px-1 py-0.5 text-[10px] font-medium"
                style={{
                  background:
                    tooltip.node.type === 'library'
                      ? '#eef2ff'
                      : tooltip.node.type === 'citing'
                        ? '#ecfdf5'
                        : '#f1f5f9',
                  color:
                    tooltip.node.type === 'library'
                      ? '#4f46e5'
                      : tooltip.node.type === 'citing'
                        ? '#059669'
                        : '#64748b',
                }}
              >
                {tooltip.node.type === 'library'
                  ? 'In library'
                  : tooltip.node.type === 'citing'
                    ? 'Newer — cites a library paper'
                    : 'Older — referenced by a library paper'}
              </span>
            </div>
            {!tooltip.node.in_library && tooltip.node.doi && (
              <p className="mt-1 text-indigo-500 dark:text-indigo-400">Click to open DOI</p>
            )}
          </div>
        )}

        {/* Node count badge */}
        <div className="absolute bottom-3 left-3 rounded-full border border-gray-200 bg-white/90 px-2.5 py-1 text-[10px] font-medium text-gray-500 backdrop-blur dark:border-slate-700 dark:bg-slate-900/90 dark:text-slate-400">
          {data.nodes.length} nodes &middot; {data.edges.length} edges
        </div>
      </div>
    </div>
  )
}

export default CitationGraph
