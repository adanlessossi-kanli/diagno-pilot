// Mock for react-native/Libraries/BatchedBridge/NativeModules
// Ensures UIManager is a plain object so jest-expo's setup.js can call
// Object.defineProperty on it without throwing "called on non-object".
const NativeModules = {
  UIManager: {
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
    setChildren: jest.fn(),
    getConstants: jest.fn(() => ({})),
  },
};

module.exports = NativeModules;
