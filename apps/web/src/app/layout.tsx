import React from 'react';

// Root layout: required by Next.js App Router.
// <html> and <body> are rendered by [locale]/layout.tsx which has locale context.
export default function RootLayout({ children }: { children: React.ReactNode }) {
  return children;
}
