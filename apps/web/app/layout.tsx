import type { ReactNode } from "react";
import { UserProvider } from "@auth0/nextjs-auth0/client";
import "./globals.css";

export const metadata = { title: "Terzo Cost Intelligence" };

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <UserProvider>
        <body className="min-h-screen bg-background text-foreground antialiased">
          {children}
        </body>
      </UserProvider>
    </html>
  );
}
