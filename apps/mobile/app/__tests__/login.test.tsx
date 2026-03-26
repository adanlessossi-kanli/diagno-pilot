/// <reference types="@jest/globals" />
import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react-native';
import { Alert } from 'react-native';
import LoginScreen from '../login';
import { colors } from '@diagno-pilot/ui/src/tokens';

// Mock expo-router
jest.mock('expo-router', () => ({
  router: { replace: jest.fn() },
  useRouter: () => ({ replace: jest.fn() }),
}));

// Mock AuthContext
const mockLogin = jest.fn();
jest.mock('../../src/contexts/AuthContext', () => ({
  useAuth: () => ({
    login: mockLogin,
  }),
}));

beforeEach(() => {
  jest.clearAllMocks();
  jest.spyOn(Alert, 'alert');
});

describe('LoginScreen', () => {
  it('renders the Diagno-Pilot brand name', () => {
    render(<LoginScreen />);
    expect(screen.getByText('Diagno-Pilot')).toBeTruthy();
  });

  it('brand name has primary color style', () => {
    render(<LoginScreen />);
    const title = screen.getByText('Diagno-Pilot');
    const flatStyle = Array.isArray(title.props.style)
      ? Object.assign({}, ...title.props.style)
      : title.props.style;
    expect(flatStyle.color).toBe(colors.primary[600]);
  });

  it('does not show error initially', () => {
    render(<LoginScreen />);
    expect(screen.queryByText('Identifiants invalides. Veuillez réessayer.')).toBeNull();
  });

  it('shows inline error text on login failure', async () => {
    mockLogin.mockRejectedValueOnce(new Error('Invalid credentials'));
    render(<LoginScreen />);

    fireEvent.changeText(screen.getByLabelText('Email'), 'test@example.com');
    fireEvent.changeText(screen.getByLabelText('Mot de passe'), 'wrongpassword');
    fireEvent.press(screen.getByLabelText('Se connecter'));

    await waitFor(() => {
      expect(screen.getByText('Identifiants invalides. Veuillez réessayer.')).toBeTruthy();
    });
  });

  it('does NOT call Alert.alert on login failure', async () => {
    mockLogin.mockRejectedValueOnce(new Error('Invalid credentials'));
    render(<LoginScreen />);

    fireEvent.changeText(screen.getByLabelText('Email'), 'test@example.com');
    fireEvent.changeText(screen.getByLabelText('Mot de passe'), 'wrongpassword');
    fireEvent.press(screen.getByLabelText('Se connecter'));

    await waitFor(() => {
      expect(screen.getByText('Identifiants invalides. Veuillez réessayer.')).toBeTruthy();
    });

    expect(Alert.alert).not.toHaveBeenCalled();
  });

  it('clears error state at the start of each login attempt', async () => {
    mockLogin.mockRejectedValueOnce(new Error('fail'));
    render(<LoginScreen />);

    fireEvent.changeText(screen.getByLabelText('Email'), 'test@example.com');
    fireEvent.changeText(screen.getByLabelText('Mot de passe'), 'wrongpassword');
    fireEvent.press(screen.getByLabelText('Se connecter'));

    await waitFor(() => {
      expect(screen.getByText('Identifiants invalides. Veuillez réessayer.')).toBeTruthy();
    });

    // Second attempt — error should be cleared before the new attempt
    mockLogin.mockResolvedValueOnce(undefined);
    fireEvent.press(screen.getByLabelText('Se connecter'));

    await waitFor(() => {
      expect(screen.queryByText('Identifiants invalides. Veuillez réessayer.')).toBeNull();
    });
  });
});
