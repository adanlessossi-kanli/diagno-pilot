export type ErrorType = 'network' | 'timeout' | 'unauthorized' | 'generic';

export const ERROR_TYPES: readonly ErrorType[] = ['network', 'timeout', 'unauthorized', 'generic'] as const;

const errorMessageMap: Record<ErrorType, { descriptionKey: string; actionKey: string }> = {
  network: {
    descriptionKey: 'errors.networkDescription',
    actionKey: 'errors.networkAction',
  },
  timeout: {
    descriptionKey: 'errors.timeout',
    actionKey: 'errors.timeoutAction',
  },
  unauthorized: {
    descriptionKey: 'errors.unauthorizedDescription',
    actionKey: 'errors.unauthorizedAction',
  },
  generic: {
    descriptionKey: 'errors.genericDescription',
    actionKey: 'errors.genericAction',
  },
};

export function buildErrorMessage(errorType: string): { descriptionKey: string; actionKey: string } {
  if (Object.hasOwn(errorMessageMap, errorType)) {
    return errorMessageMap[errorType as ErrorType];
  }
  return errorMessageMap.generic;
}
