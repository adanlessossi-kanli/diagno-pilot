// Manual mock for expo-localization (not installed in test environment)
module.exports = {
  getLocales: jest.fn(() => []),
  getCalendars: jest.fn(() => []),
  locale: 'fr-TG',
  locales: ['fr-TG'],
  timezone: 'Africa/Lome',
  isRTL: false,
};
