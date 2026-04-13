// Mock for @react-native-community/netinfo
const listeners = [];

const NetInfo = {
  addEventListener: jest.fn((callback) => {
    listeners.push(callback);
    // Immediately call with default connected state
    callback({ isConnected: true, isInternetReachable: true });
    return () => {
      const idx = listeners.indexOf(callback);
      if (idx >= 0) listeners.splice(idx, 1);
    };
  }),
  fetch: jest.fn(() =>
    Promise.resolve({ isConnected: true, isInternetReachable: true })
  ),
  // Test helper to simulate connectivity changes
  __listeners: listeners,
};

module.exports = NetInfo;
module.exports.default = NetInfo;
