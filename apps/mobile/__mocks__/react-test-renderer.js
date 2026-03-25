// Re-export react-test-renderer but ensure it uses the local React 18 instance
// This prevents the React 19 (root) vs React 18 (mobile) version mismatch.
const React = require('../node_modules/react');
const renderer = jest.requireActual('react-test-renderer');
module.exports = renderer;
