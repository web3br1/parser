import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Context Builder",
  description: "Context Builder Empresarial"
};

export default function RootLayout({
  children
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="pt-BR">
      <body>{children}</body>
    </html>
  );
}
