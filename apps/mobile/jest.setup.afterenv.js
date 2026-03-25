// This file runs after the test framework is installed.
// Configure @testing-library/react-native with the correct host component names
// for React Native 0.76.x (which uses RCT-prefixed types in the test renderer).
const { configure } = require('@testing-library/react-native');

configure({
  hostComponentNames: {
    text: 'RCTText',
    textInput: 'RCTSinglelineTextInputView',
    image: 'RCTImageView',
    switch: 'RCTSwitch',
    scrollView: 'RCTScrollView',
    modal: 'RCTModalHostView',
  },
});
