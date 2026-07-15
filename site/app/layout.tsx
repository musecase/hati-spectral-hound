import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  metadataBase: new URL("https://hati-spectral-hound.amarygma.chatgpt.site"),
  title: {
    default: "HATI — Spectral Hound",
    template: "%s | HATI",
  },
  description: "An AI farm bouncer that knows when not to act.",
  icons: { icon: "/favicon.svg" },
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
