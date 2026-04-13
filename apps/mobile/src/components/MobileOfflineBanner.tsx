// REQ-8.2, REQ-8.3: Persistent offline banner for mobile using @react-native-community/netinfo
import React, { useEffect, useState } from 'react';
import { View, Text, StyleSheet } from 'react-native';
import NetInfo from '@react-native-community/netinfo';
import { colors, spacing, typography } from '@diagno-pilot/ui/src/tokens';

const DEFAULT_LABEL = 'You are offline. Please check your internet connection.';

export interface MobileOfflineBannerProps {
  /** Optional label text — pass a translated string or rely on the English default. */
  label?: string;
}

export function MobileOfflineBanner({
  label = DEFAULT_LABEL,
}: MobileOfflineBannerProps): JSX.Element | null {
  const [isOffline, setIsOffline] = useState(false);

  useEffect(() => {
    const unsubscribe = NetInfo.addEventListener((state) => {
      setIsOffline(state.isConnected === false);
    });
    return () => unsubscribe();
  }, []);

  if (!isOffline) return null;

  return (
    <View style={styles.container} accessibilityRole="alert">
      <Text style={styles.text}>{label}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    backgroundColor: colors.error.border,
    paddingVertical: spacing[2],
    paddingHorizontal: spacing[4],
    alignItems: 'center',
  },
  text: {
    color: '#FFFFFF',
    fontSize: typography.sm,
    fontWeight: '600',
    textAlign: 'center',
  },
});
