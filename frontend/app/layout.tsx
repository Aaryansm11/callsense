import "./globals.css";
import type { Metadata } from "next";
import { Header } from "@/components/Header";

export const metadata: Metadata = {
  title: "CallSense · SkilloVilla",
  description: "Sales-call intelligence for SkilloVilla — scoring, mis-selling flags, coaching.",
  icons: { icon: "/favicon-32x32.png" },
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body>
        <Header />
        <main className="mx-auto max-w-7xl px-6 py-8">{children}</main>
      </body>
    </html>
  );
}
