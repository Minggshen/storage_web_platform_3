/**
 * Unified semantic color palette for all charts (Recharts + SVG export).
 *
 * Semantics:
 *   Revenue / income:   blue & green family
 *   Cost / penalty:     red & orange family
 *   Recommended:        gold star — emphasis only
 *   Feasible:           green
 *   Infeasible:         gray
 *   Baseline (pre-storage):   gray dashed
 *   Optimized (post-storage): dark-blue solid
 *   SOC:                teal solid
 *   Tariff:             purple stepAfter
 *   Charge power:       negative red/orange bars
 *   Discharge power:    positive green/blue bars
 */

export const SEMANTIC_COLORS = {
  // ── Revenue / income (blue → green) ──
  revenue: {
    primary: '#2563eb',    // blue-600 — arbitrage, main income
    secondary: '#059669',  // emerald-600 — demand saving
    tertiary: '#0891b2',   // cyan-600 — auxiliary / capacity
    quaternary: '#65a30d', // lime-600 — capacity revenue
    lossReduction: '#0f766e', // teal-700 — loss reduction (distinct from capacity)
  },

  // ── Cost / penalty (red → orange) ──
  cost: {
    primary: '#dc2626',    // red-600 — penalty, degradation
    secondary: '#d97706',  // amber-600 — O&M
    tertiary: '#ea580c',   // orange-600 — replacement
  },

  // ── Status markers ──
  recommended: '#eab308',  // gold — recommended solution star
  feasible: '#16a34a',     // green-600
  infeasible: '#9ca3af',   // gray-400

  // ── Before / after comparison ──
  baseline: '#6b7280',     // gray-500 — pre-storage (always dashed)
  optimized: '#1e3a5f',   // dark-blue — post-storage (always solid)

  // ── Curves ──
  soc: '#0d9488',          // teal-600
  tariff: '#7c3aed',       // violet-600 (must use stepAfter, never smooth)

  // ── Power bars ──
  charge: '#ef4444',       // red-500 — charging (negative direction)
  discharge: '#22c55e',    // green-500 — discharging (positive direction)

  // ── Reference / zero / grid ──
  zeroLine: '#111827',     // gray-900
  constraint: '#b91c1c',   // red-700 — limit / threshold lines
  grid: '#e5e7eb',         // gray-200

  // ── Neutral fallback ──
  neutral: '#6b7280',      // gray-500
} as const;

/** Stroke-dasharray values keyed by line role. */
export const LINE_STYLES = {
  solid: undefined,
  dashed: '5,5',
  dashDot: '8,4,2,4',
} as const;

/** Default chart dimensions for exported SVG (report). */
export const CHART_DIMS = {
  width: 760,
  height: 440,
  margin: { top: 30, right: 50, bottom: 70, left: 70 },
} as const;
