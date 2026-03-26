import { colors } from '@diagno-pilot/ui/src/tokens';

export function getProbabilityColor(p: number): string {
  if (p >= 0.7) return colors.success.border;
  if (p >= 0.4) return colors.warning.border;
  return colors.error.border;
}
