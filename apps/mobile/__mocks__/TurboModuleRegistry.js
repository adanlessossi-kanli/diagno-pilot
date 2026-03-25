// Mock TurboModuleRegistry to avoid __fbBatchedBridgeConfig invariant errors
// in the Jest test environment.
const TurboModuleRegistry = {
  get: jest.fn(() => null),
  getEnforcing: jest.fn((name) => {
    // Return minimal mocks for known modules
    const mocks = {
      PlatformConstants: {
        getConstants: () => ({
          isTesting: true,
          reactNativeVersion: { major: 0, minor: 76, patch: 5 },
          osVersion: '17.0',
          systemName: 'iOS',
          interfaceIdiom: 'phone',
          forceTouchAvailable: false,
          isDisableAnimations: false,
        }),
      },
    };
    return mocks[name] || {};
  }),
};

module.exports = TurboModuleRegistry;
