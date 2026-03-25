// Set up __fbBatchedBridgeConfig before react-native modules load.
// This prevents the invariant error in NativeModules.js (RN 0.76.x).
global.__fbBatchedBridgeConfig = {
  remoteModuleConfig: [],
};

// Set up __turboModuleProxy to provide native modules that
// TurboModuleRegistry.getEnforcing() requires in the test environment.
// RN 0.76.x uses TurboModules for core modules like PlatformConstants, DeviceInfo, etc.
const platformConstantsMock = {
  getConstants: () => ({
    isTesting: true,
    reactNativeVersion: { major: 0, minor: 76, patch: 5 },
    osVersion: '17.0',
    systemName: 'iOS',
    interfaceIdiom: 'phone',
    forceTouchAvailable: false,
    isDisableAnimations: false,
  }),
};

const deviceInfoMock = {
  getConstants: () => ({
    Dimensions: {
      window: { width: 375, height: 812, scale: 3, fontScale: 1 },
      screen: { width: 375, height: 812, scale: 3, fontScale: 1 },
    },
  }),
};

const appearanceMock = {
  getColorScheme: () => 'light',
  addListener: () => ({ remove: () => {} }),
  removeListener: () => {},
};

const accessibilityInfoMock = {
  getConstants: () => ({
    reduceMotionEnabled: false,
    reduceTransparencyEnabled: false,
    highTextContrastEnabled: false,
    invertColorsEnabled: false,
    screenReaderEnabled: false,
    boldTextEnabled: false,
    grayscaleEnabled: false,
    prefersCrossFadeTransitions: false,
  }),
  isReduceMotionEnabled: () => Promise.resolve(false),
  isScreenReaderEnabled: () => Promise.resolve(false),
  addEventListener: () => ({ remove: () => {} }),
  removeEventListener: () => {},
  announceForAccessibility: () => {},
};

const networkingMock = {
  sendRequest: jest.fn(),
  abortRequest: jest.fn(),
  clearCookies: jest.fn(),
};

const timingMock = {
  createTimer: jest.fn(),
  deleteTimer: jest.fn(),
};

const sourceMock = {
  getConstants: () => ({}),
};

const uiManagerMock = {
  getViewManagerConfig: jest.fn(() => ({})),
  hasViewManagerConfig: jest.fn(() => false),
  createView: jest.fn(),
  updateView: jest.fn(),
  manageChildren: jest.fn(),
  setChildren: jest.fn(),
  dispatchViewManagerCommand: jest.fn(),
  measure: jest.fn(),
  measureInWindow: jest.fn(),
  measureLayout: jest.fn(),
  measureLayoutRelativeToParent: jest.fn(),
  findSubviewIn: jest.fn(),
  viewIsDescendantOf: jest.fn(),
  setJSResponder: jest.fn(),
  clearJSResponder: jest.fn(),
  configureNextLayoutAnimation: jest.fn(),
  removeSubviewsFromContainerWithID: jest.fn(),
  replaceExistingNonRootView: jest.fn(),
  getConstants: jest.fn(() => ({
    customBubblingEventTypes: {},
    customDirectEventTypes: {},
  })),
  blur: jest.fn(),
  focus: jest.fn(),
};

const devSettingsMock = {
  reload: jest.fn(),
  onFastRefresh: jest.fn(),
  setHotLoadingEnabled: jest.fn(),
  setIsShakeToShowDevMenuEnabled: jest.fn(),
  setProfilingEnabled: jest.fn(),
  setRemoteDebuggingEnabled: jest.fn(),
  addListener: jest.fn(() => ({ remove: jest.fn() })),
  removeListeners: jest.fn(),
};

const imageLoaderMock = {
  prefetchImage: jest.fn(() => Promise.resolve()),
  prefetchImageWithMetadata: jest.fn(() => Promise.resolve()),
  getSize: jest.fn((uri, success) => process.nextTick(() => success(320, 240))),
  getSizeWithHeaders: jest.fn((uri, headers, success) =>
    process.nextTick(() => success(320, 240))
  ),
  queryCache: jest.fn(() => Promise.resolve({})),
  abortRequest: jest.fn(),
};

const statusBarMock = {
  getHeight: jest.fn(() => 44),
  setHidden: jest.fn(),
  setBarStyle: jest.fn(),
  setNetworkActivityIndicatorVisible: jest.fn(),
  setBackgroundColor: jest.fn(),
  setTranslucent: jest.fn(),
  getConstants: jest.fn(() => ({ HEIGHT: 44, DEFAULT_BACKGROUND_COLOR: 0 })),
};

const keyboardMock = {
  addListener: jest.fn(() => ({ remove: jest.fn() })),
  removeListeners: jest.fn(),
  removeListener: jest.fn(),
  dismiss: jest.fn(),
  scheduleLayoutAnimation: jest.fn(),
};

const animatedMock = {
  createAnimatedComponent: jest.fn((c) => c),
  Value: jest.fn(() => ({
    setValue: jest.fn(),
    interpolate: jest.fn(() => ({ interpolate: jest.fn() })),
    addListener: jest.fn(),
    removeListener: jest.fn(),
  })),
};

const safeAreaMock = {
  getConstants: jest.fn(() => ({
    initialWindowMetrics: {
      insets: { top: 44, right: 0, bottom: 34, left: 0 },
      frame: { x: 0, y: 0, width: 375, height: 812 },
    },
  })),
};

global.__turboModuleProxy = (name) => {
  const modules = {
    PlatformConstants: platformConstantsMock,
    PlatformConstantsIOS: platformConstantsMock,
    NativePlatformConstantsIOS: platformConstantsMock,
    DeviceInfo: deviceInfoMock,
    NativeDeviceInfo: deviceInfoMock,
    Appearance: appearanceMock,
    NativeAppearance: appearanceMock,
    AccessibilityInfo: accessibilityInfoMock,
    NativeAccessibilityInfo: accessibilityInfoMock,
    Networking: networkingMock,
    Timing: timingMock,
    SourceCode: sourceMock,
    NativeSourceCode: sourceMock,
    UIManager: uiManagerMock,
    NativeUIManager: uiManagerMock,
    ImageLoader: imageLoaderMock,
    NativeImageLoader: imageLoaderMock,
    StatusBarManager: statusBarMock,
    NativeStatusBarManager: statusBarMock,
    KeyboardObserver: keyboardMock,
    NativeKeyboardObserver: keyboardMock,
    Animated: animatedMock,
    RNCSafeAreaProvider: safeAreaMock,
    SafeAreaManager: safeAreaMock,
    DevSettings: devSettingsMock,
    NativeDevSettings: devSettingsMock,
  };
  return modules[name] || null;
};

