import type { Config } from 'tailwindcss';
import { colors, radius, shadow } from '../../packages/ui/src/tokens';

const config: Config = {
  content: [
    './src/pages/**/*.{js,ts,jsx,tsx,mdx}',
    './src/components/**/*.{js,ts,jsx,tsx,mdx}',
    './src/app/**/*.{js,ts,jsx,tsx,mdx}',
  ],
  theme: {
    extend: {
      colors: {
        primary: {
          50:  colors.primary[50],
          100: colors.primary[100],
          300: colors.primary[300],
          600: colors.primary[600],
          700: colors.primary[700],
        },
        neutral: {
          50:  colors.neutral[50],
          100: colors.neutral[100],
          200: colors.neutral[200],
          400: colors.neutral[400],
          500: colors.neutral[500],
          700: colors.neutral[700],
          900: colors.neutral[900],
        },
        success: {
          bg:     colors.success.bg,
          border: colors.success.border,
          text:   colors.success.text,
        },
        warning: {
          bg:     colors.warning.bg,
          border: colors.warning.border,
          text:   colors.warning.text,
        },
        error: {
          bg:     colors.error.bg,
          border: colors.error.border,
          text:   colors.error.text,
        },
        info: {
          bg:     colors.info.bg,
          border: colors.info.border,
          text:   colors.info.text,
        },
      },
      borderRadius: {
        sm: `${radius.sm}px`,
        md: `${radius.md}px`,
        lg: `${radius.lg}px`,
        xl: `${radius.xl}px`,
      },
      boxShadow: {
        sm: shadow.web.sm,
        md: shadow.web.md,
        lg: shadow.web.lg,
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', 'sans-serif'],
      },
      keyframes: {
        'slide-in-top': {
          from: { transform: 'translateY(-100%)', opacity: '0' },
          to:   { transform: 'translateY(0)',     opacity: '1' },
        },
      },
      animation: {
        'slide-in-top': 'slide-in-top 250ms ease-out forwards',
      },
    },
  },
  plugins: [],
};

export default config;
