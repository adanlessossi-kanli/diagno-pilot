/**
 * Unit tests for MobileOfflineBanner
 *
 * Validates: Requirements 8.2, 8.3
 * - Shows persistent banner when isConnected === false
 * - Auto-hides when connectivity is restored
 * - Uses accessibilityRole="alert"
 * - Accepts optional label prop with English default
 */
import React from 'react';
import { render, screen, act } from '@testing-library/react-native';
import { MobileOfflineBanner } from '../MobileOfflineBanner';

// Get reference to the mock's listener list
const NetInfoMock = require('@react-native-community/netinfo');

function simulateConnectivity(isConnected: boolean) {
  act(() => {
    for (const listener of NetInfoMock.__listeners) {
      listener({ isConnected, isInternetReachable: isConnected });
    }
  });
}

beforeEach(() => {
  NetInfoMock.__listeners.length = 0;
  NetInfoMock.addEventListener.mockClear();
});

describe('MobileOfflineBanner', () => {
  it('renders nothing when device is online', () => {
    render(<MobileOfflineBanner />);
    expect(
      screen.queryByText('You are offline. Please check your internet connection.')
    ).toBeNull();
  });

  it('shows banner when isConnected === false', () => {
    render(<MobileOfflineBanner />);
    simulateConnectivity(false);

    const banner = screen.UNSAFE_getByProps({ accessibilityRole: 'alert' });
    expect(banner).toBeTruthy();
    expect(
      screen.getByText('You are offline. Please check your internet connection.')
    ).toBeTruthy();
  });

  it('auto-hides when connectivity is restored (Req 8.3)', () => {
    render(<MobileOfflineBanner />);
    simulateConnectivity(false);
    expect(
      screen.getByText('You are offline. Please check your internet connection.')
    ).toBeTruthy();

    simulateConnectivity(true);
    expect(
      screen.queryByText('You are offline. Please check your internet connection.')
    ).toBeNull();
  });

  it('renders custom label when provided', () => {
    render(<MobileOfflineBanner label="Hors ligne" />);
    simulateConnectivity(false);
    expect(screen.getByText('Hors ligne')).toBeTruthy();
  });

  it('subscribes to NetInfo on mount and unsubscribes on unmount', () => {
    const { unmount } = render(<MobileOfflineBanner />);
    expect(NetInfoMock.addEventListener).toHaveBeenCalledTimes(1);

    const listenerCountBefore = NetInfoMock.__listeners.length;
    unmount();
    expect(NetInfoMock.__listeners.length).toBeLessThan(listenerCountBefore);
  });
});
