// REQ-2.2, REQ-2.4, REQ-2.6: Profile screen with inline language selector
import { View, Text, TouchableOpacity, ActivityIndicator, StyleSheet } from 'react-native';
import { useAuth } from '../../src/contexts/AuthContext';
import { useI18n } from '../../src/contexts/I18nContext';

export default function ProfileScreen() {
  const { user, isLoading, logout } = useAuth();
  const { locale, setLocale } = useI18n();

  if (isLoading) {
    return (
      <View style={styles.center}>
        <ActivityIndicator size="large" color="#2563eb" />
      </View>
    );
  }

  return (
    <View style={styles.container}>
      <View style={styles.card}>
        <Text style={styles.avatar}>👤</Text>
        <Text style={styles.name}>{user?.fullName ?? '—'}</Text>
        <Text style={styles.email}>{user?.email ?? '—'}</Text>
        <View style={styles.roleBadge}>
          <Text style={styles.roleText}>{user?.role ?? '—'}</Text>
        </View>
      </View>

      {/* REQ-2.2: Inline language selector */}
      <View style={styles.langSection}>
        <Text style={styles.langLabel}>Langue / Language</Text>
        <View style={styles.langSelector}>
          <TouchableOpacity
            style={[styles.langButton, locale.startsWith('fr') && styles.langButtonActive]}
            onPress={() => void setLocale('fr-TG')}
            accessibilityRole="button"
            accessibilityLabel="Français"
            accessibilityState={{ selected: locale.startsWith('fr') }}
          >
            <Text style={[styles.langButtonText, locale.startsWith('fr') && styles.langButtonTextActive]}>
              FR
            </Text>
          </TouchableOpacity>
          <TouchableOpacity
            style={[styles.langButton, locale === 'en' && styles.langButtonActive]}
            onPress={() => void setLocale('en')}
            accessibilityRole="button"
            accessibilityLabel="English"
            accessibilityState={{ selected: locale === 'en' }}
          >
            <Text style={[styles.langButtonText, locale === 'en' && styles.langButtonTextActive]}>
              EN
            </Text>
          </TouchableOpacity>
        </View>
      </View>

      <TouchableOpacity
        style={styles.logoutButton}
        onPress={() => void logout()}
        accessibilityRole="button"
        accessibilityLabel="Se déconnecter"
      >
        <Text style={styles.logoutText}>Se déconnecter</Text>
      </TouchableOpacity>
    </View>
  );
}

const styles = StyleSheet.create({
  center: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
  },
  container: {
    flex: 1,
    backgroundColor: '#f9fafb',
    padding: 24,
    alignItems: 'center',
  },
  card: {
    backgroundColor: '#fff',
    borderRadius: 12,
    padding: 24,
    alignItems: 'center',
    width: '100%',
    shadowColor: '#000',
    shadowOpacity: 0.06,
    shadowRadius: 8,
    shadowOffset: { width: 0, height: 2 },
    elevation: 2,
    marginBottom: 24,
  },
  avatar: {
    fontSize: 48,
    marginBottom: 12,
  },
  name: {
    fontSize: 20,
    fontWeight: '700',
    color: '#111827',
    marginBottom: 4,
  },
  email: {
    fontSize: 14,
    color: '#6b7280',
    marginBottom: 12,
  },
  roleBadge: {
    backgroundColor: '#dbeafe',
    borderRadius: 999,
    paddingHorizontal: 12,
    paddingVertical: 4,
  },
  roleText: {
    fontSize: 12,
    fontWeight: '600',
    color: '#1d4ed8',
    textTransform: 'capitalize',
  },
  langSection: {
    width: '100%',
    backgroundColor: '#fff',
    borderRadius: 12,
    padding: 16,
    marginBottom: 24,
    shadowColor: '#000',
    shadowOpacity: 0.06,
    shadowRadius: 8,
    shadowOffset: { width: 0, height: 2 },
    elevation: 2,
    alignItems: 'center',
  },
  langLabel: {
    fontSize: 13,
    color: '#6b7280',
    marginBottom: 12,
    fontWeight: '500',
  },
  langSelector: {
    flexDirection: 'row',
    gap: 12,
  },
  langButton: {
    paddingVertical: 8,
    paddingHorizontal: 24,
    borderRadius: 8,
    borderWidth: 1.5,
    borderColor: '#d1d5db',
    backgroundColor: '#f9fafb',
  },
  langButtonActive: {
    borderColor: '#2563eb',
    backgroundColor: '#2563eb',
  },
  langButtonText: {
    fontSize: 14,
    fontWeight: '700',
    color: '#374151',
  },
  langButtonTextActive: {
    color: '#fff',
  },
  logoutButton: {
    backgroundColor: '#dc2626',
    borderRadius: 8,
    paddingVertical: 12,
    paddingHorizontal: 32,
    width: '100%',
    alignItems: 'center',
  },
  logoutText: {
    color: '#fff',
    fontWeight: '700',
    fontSize: 15,
  },
});
