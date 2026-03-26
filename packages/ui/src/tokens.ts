// Design token module — plain TS constants, no React, no side effects.
// Consumed by both apps/web (Tailwind config, build-time) and apps/mobile (StyleSheets, runtime).

export const colors = {
  primary: {
    50:  '#EFF6FF',
    100: '#DBEAFE',
    300: '#93C5FD',
    600: '#2563EB',
    700: '#1D4ED8',
  },
  neutral: {
    50:  '#F9FAFB',
    100: '#F3F4F6',
    200: '#E5E7EB',
    400: '#9CA3AF',
    500: '#6B7280',
    700: '#374151',
    900: '#111827',
  },
  // Semantic tokens — each has bg, border, text
  success: {
    bg:     '#F0FDF4',
    border: '#16A34A',
    text:   '#14532D',
  },
  warning: {
    bg:     '#FFFBEB',
    border: '#D97706',
    text:   '#78350F',
  },
  error: {
    bg:     '#FEF2F2',
    border: '#DC2626',
    text:   '#7F1D1D',
  },
  info: {
    bg:     '#EFF6FF',
    border: '#2563EB',
    text:   '#1E3A5F',
  },
} as const;

export const typography = {
  xs:   12,  // px / sp — range [11, 12]
  sm:   14,  // range [13, 14]
  base: 16,  // range [15, 16]
  lg:   20,  // range [18, 20]
} as const;

export const spacing = {
  1:  4,
  2:  8,
  3:  12,
  4:  16,
  6:  24,
  8:  32,
  12: 48,
} as const;

export const radius = {
  sm:   4,
  md:   8,
  lg:   12,
  xl:   16,
  full: 9999,
} as const;

export const shadow = {
  // Web: CSS box-shadow strings
  web: {
    sm: '0 1px 2px 0 rgb(0 0 0 / 0.05)',
    md: '0 4px 6px -1px rgb(0 0 0 / 0.1), 0 2px 4px -2px rgb(0 0 0 / 0.1)',
    lg: '0 10px 15px -3px rgb(0 0 0 / 0.1), 0 4px 6px -4px rgb(0 0 0 / 0.1)',
  },
  // Mobile: React Native elevation integers
  mobile: {
    sm: 2,
    md: 4,
    lg: 8,
  },
} as const;
