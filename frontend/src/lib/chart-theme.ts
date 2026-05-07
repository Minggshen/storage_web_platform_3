/** Centralized Recharts theme configuration using CSS variables */
export const chartTheme = {
  colors: {
    primary: 'var(--chart-1)',
    secondary: 'var(--chart-2)',
    tertiary: 'var(--chart-3)',
    quaternary: 'var(--chart-4)',
    quinary: 'var(--chart-5)',
    grid: 'var(--border)',
    text: 'var(--muted-foreground)',
  },
  commonProps: {
    strokeDasharray: '3 3',
    stroke: 'var(--border)',
    strokeOpacity: 0.6,
  },
} as const;
