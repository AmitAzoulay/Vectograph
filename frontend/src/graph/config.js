/**
 * Central styling + layout configuration for the force graph.
 *
 * Keeping colours, sizes and physics constants here means the graph engine,
 * the legend and the drawer never drift out of sync.
 */

// Colour-code nodes by architectural role.
export const NODE_COLORS = {
  Application: '#0891b2', // cyan   - logical app / microservice root
  Client: '#7c3aed', // purple - inbound caller / end user
  Endpoint: '#16a34a', // green  - exposed attack surface
  Database: '#2563eb', // blue   - data stores
  ExternalAPI: '#dc2626', // red  - third party dependencies
  Service: '#64748b', // slate  - internal files / modules
}

// Colour-code edges by relationship type.
export const REL_COLORS = {
  EXPOSES: '#16a34a',
  QUERIES: '#2563eb',
  REQUESTS: '#dc2626',
  CALLS: '#475569',
  HAS_COMPONENT: '#0891b2',
  USES: '#7c3aed',
}

// Display labels for the legend, ordered by importance to a pentester.
export const NODE_META = {
  Application: { label: 'Application', hint: 'Logical service / app root' },
  Client: { label: 'Client / User', hint: 'Inbound caller' },
  Database: { label: 'Database', hint: 'SQL / NoSQL / cache' },
  ExternalAPI: { label: 'External API', hint: 'Third party call' },
  Endpoint: { label: 'Endpoint', hint: 'Exposed HTTP route' },
  Service: { label: 'Service', hint: 'Internal file / module' },
}

// The nodes visible on the default (architecture) network map.
export const ARCHITECTURE_TYPES = new Set([
  'Application',
  'Client',
  'Database',
  'ExternalAPI',
])

export function isArchitectureType(type) {
  return ARCHITECTURE_TYPES.has(type)
}

// Node radius in graph units, by type. The app root and attack surface are
// drawn larger so they draw the eye.
export function radiusForType(type) {
  switch (type) {
    case 'Application':
      return 11
    case 'Client':
      return 7.5
    case 'Endpoint':
    case 'Database':
    case 'ExternalAPI':
      return 6
    default:
      return 4.5
  }
}

export function colorForType(type) {
  return NODE_COLORS[type] || NODE_COLORS.Service
}

export function relColor(type) {
  return REL_COLORS[type] || REL_COLORS.CALLS
}

// Convert a hex colour to an rgba() string with the given alpha.
// Used to "dim" parts of the graph when a node is hovered.
export function withAlpha(hex, alpha) {
  const clean = hex.replace('#', '')
  const r = parseInt(clean.substring(0, 2), 16)
  const g = parseInt(clean.substring(2, 4), 16)
  const b = parseInt(clean.substring(4, 6), 16)
  return `rgba(${r}, ${g}, ${b}, ${alpha})`
}

// Physics tuning for d3-force. Lower velocityDecay = more floaty/organic.
export const PHYSICS = {
  // How quickly the simulation "cools down" from its initial energy.
  d3AlphaDecay: 0.0228,
  // Friction: 0 = no friction (chaotic), 1 = frozen.
  d3VelocityDecay: 0.32,
  // Link distance and repulsion shape the layout.
  linkDistance: 60,
  linkStrength: 0.55,
  chargeStrength: -140,
  // Extra ticks before first paint so the graph starts already settled.
  warmupTicks: 40,
  cooldownTicks: 350,
}
