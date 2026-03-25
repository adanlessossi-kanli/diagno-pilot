import { View, Text, TouchableOpacity, ActivityIndicator, StyleSheet } from 'react-native';
import { useAuth } from '../../src/contexts/AuthContext';

export default function ProfileScreen() {
  const { user, isLoading, logout } = useAuth();

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
