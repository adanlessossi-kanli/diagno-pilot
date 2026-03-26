// Root layout — wraps the entire app with AuthProvider and I18nProvider
import { Stack } from 'expo-router';
import { AuthProvider } from '../src/contexts/AuthContext';
import { I18nProvider } from '../src/contexts/I18nContext';

export default function RootLayout() {
  return (
    <I18nProvider>
      <AuthProvider>
        <Stack screenOptions={{ headerShown: false }} />
      </AuthProvider>
    </I18nProvider>
  );
}
