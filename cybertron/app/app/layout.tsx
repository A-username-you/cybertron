import "./globals.css";

export const metadata = {
  title: "Cybertron",
  description: "Autonomous bug-bounty agent — recon, scan, exploit, report.",
};

export const viewport = {
  width: "device-width",
  initialScale: 1,
  maximumScale: 5, // allow pinch-zoom, never lock it - that's an accessibility anti-pattern
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
