import type { CapacitorConfig } from "@capacitor/cli";

const config: CapacitorConfig = {
  // Reverse-DNS id, fixed for the life of the app: changing it after the first
  // store submission creates a DIFFERENT app, not an update. Confirm this
  // against the domain before the first upload.
  appId: "com.brunoaiworkforce.app",
  appName: "Bruno AI Workforce",

  // Populated by `npm run build:web` from the Next static export. Not committed.
  webDir: "www",

  // The app ships its own UI and calls the API over HTTPS. Serving the bundle
  // over https://localhost (rather than the default file://) keeps the WebView
  // on a secure origin, so localStorage — where the auth token lives — persists
  // and fetch() is not treated as mixed content.
  server: {
    androidScheme: "https",
  },

  android: {
    // No cleartext: the backend is HTTPS-only in production.
    allowMixedContent: false,
  },

  ios: {
    contentInset: "always",
  },
};

export default config;
