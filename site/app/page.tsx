import type { Metadata } from "next";
import { HatiExperience } from "./HatiExperience";

export const metadata: Metadata = {
  title: "HATI — Spectral Hound",
  description:
    "A camera-triggered AI farm bouncer that knows when not to act.",
  openGraph: {
    title: "HATI — Spectral Hound",
    description:
      "Five-frame evidence. Deterministic safety rules. Humane, targeted predator deterrence.",
    images: [{ url: "/og.png", width: 1536, height: 1024 }],
  },
  twitter: {
    card: "summary_large_image",
    title: "HATI — Spectral Hound",
    description: "An AI farm bouncer that knows when not to act.",
    images: ["/og.png"],
  },
};

export default function Home() {
  return <HatiExperience />;
}
