// Button variant class strings for use with Tailwind CSS (web only).
// Import these in web components to apply consistent button styling.

export const buttonVariants = {
  primary:
    'bg-primary-600 text-white hover:bg-primary-700 rounded-md px-4 py-2 text-sm font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed',
  secondary:
    'border border-neutral-200 text-neutral-700 hover:bg-neutral-50 rounded-md px-4 py-2 text-sm font-medium transition-colors',
  ghost:
    'text-primary-600 hover:text-primary-700 px-4 py-2 text-sm font-medium transition-colors',
} as const;

export type ButtonVariant = keyof typeof buttonVariants;
