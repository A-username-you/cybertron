/** @type {import('next').NextConfig} */
const nextConfig = {
  // Static export — this is fine now, because no page here depends on an
  // API route for agent behavior. All dynamic work happens in the runtime
  // process over WebSocket, which works identically whether this HTML is
  // served by `next dev`, opened via file:// in Electron, or hosted on a
  // static CDN.
  output: "export",
  images: { unoptimized: true },
};

module.exports = nextConfig;
