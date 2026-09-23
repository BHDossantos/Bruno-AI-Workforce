/** @type {import('next').NextConfig} */

// The same source tree builds two ways:
//   default        -> output: "standalone", the server bundle Render deploys
//   MOBILE_BUILD=1 -> output: "export", a static bundle Capacitor ships inside
//                     the iOS and Android apps
// Every page is a client component talking to NEXT_PUBLIC_API_URL, so the export
// needs no server at runtime. trailingSlash keeps directory-style URLs resolving
// from the local filesystem inside the WebView.
const mobile = process.env.MOBILE_BUILD === "1";

const nextConfig = {
  reactStrictMode: true,
  ...(mobile
    ? { output: "export", trailingSlash: true, images: { unoptimized: true } }
    : { output: "standalone" }),
};

module.exports = nextConfig;
