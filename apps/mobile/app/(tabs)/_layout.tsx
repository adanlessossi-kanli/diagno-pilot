// Tab navigation layout with RBAC — REQ 8.1, 8.2, 8.3, 8.4, 8.5
import { useEffect } from 'react';
import { Tabs, useRouter, useSegments } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { colors } from '@diagno-pilot/ui/src/tokens';
import { useAuth } from '../../src/contexts/AuthContext';
import type { UserRole } from '@diagno-pilot/types';

/** Roles that have access to medical features (REQ 8.1, 8.2, 8.4) */
export const MEDICAL_ROLES: UserRole[] = ['medecin', 'infirmière', 'admin'];

/** All screens and which roles may access them */
export const SCREEN_PERMISSIONS: Record<string, UserRole[]> = {
  diagnose: MEDICAL_ROLES,
  chat: MEDICAL_ROLES,
  patients: MEDICAL_ROLES,
  profile: ['admin', 'medecin', 'infirmière'],
  qa: ['admin', 'medecin', 'infirmière', 'guest'],
};

export default function TabsLayout() {
  const { user } = useAuth();
  const role: UserRole = user?.role ?? 'guest';
  const router = useRouter();
  const segments = useSegments();

  const isMedical = MEDICAL_ROLES.includes(role);

  // REQ 8.5: redirect to profile if navigating to an unauthorized screen
  useEffect(() => {
    const currentScreen = segments[segments.length - 1] as string | undefined;
    if (!currentScreen) return;

    const allowed = SCREEN_PERMISSIONS[currentScreen];
    if (allowed && !allowed.includes(role)) {
      router.replace('/(tabs)/profile' as never);
    }
  }, [segments, role, router]);

  return (
    <Tabs
      screenOptions={{
        tabBarActiveTintColor: colors.primary[600],
        tabBarInactiveTintColor: colors.neutral[400],
        headerStyle: { backgroundColor: colors.primary[600] },
        headerTintColor: '#fff',
        headerTitleStyle: { fontWeight: '700' },
      }}
    >
      {/* Medical tabs — REQ 8.1, 8.2, 8.4 */}
      <Tabs.Screen
        name="diagnose"
        options={{
          title: 'Diagnostic',
          href: isMedical ? undefined : null,
          tabBarIcon: ({ color }) => <Ionicons name="medkit-outline" size={22} color={color} />,
        }}
      />
      <Tabs.Screen
        name="chat"
        options={{
          title: 'Chat Q&A',
          href: isMedical ? undefined : null,
          tabBarIcon: ({ color }) => <Ionicons name="chatbubble-outline" size={22} color={color} />,
        }}
      />
      <Tabs.Screen
        name="patients"
        options={{
          title: 'Patients',
          href: isMedical ? undefined : null,
          tabBarIcon: ({ color }) => <Ionicons name="people-outline" size={22} color={color} />,
        }}
      />
      {/* QA tab — REQ 8.3: visible for all roles including guest */}
      <Tabs.Screen
        name="qa"
        options={{
          title: 'Assistant QA',
          tabBarIcon: ({ color }) => <Ionicons name="help-circle-outline" size={22} color={color} />,
        }}
      />
      {/* Profile tab — REQ 8.3: hidden for guest */}
      <Tabs.Screen
        name="profile"
        options={{
          title: 'Profil',
          href: role !== 'guest' ? undefined : null,
          tabBarIcon: ({ color }) => <Ionicons name="person-outline" size={22} color={color} />,
        }}
      />
    </Tabs>
  );
}
