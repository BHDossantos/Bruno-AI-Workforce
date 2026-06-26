import "./globals.css";
import type { Metadata } from "next";
import Sidebar from "@/components/Sidebar";
import ApiStatusBanner from "@/components/ApiStatusBanner";
import VoiceCommand from "@/components/VoiceCommand";

export const metadata: Metadata = {
  title: "Bruno AI Workforce",
  description: "Private AI workforce platform — daily executive workflows",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <div className="flex min-h-screen flex-col md:flex-row">
          <Sidebar />
          <main className="flex-1 overflow-x-hidden">
            <ApiStatusBanner />
            <div className="p-4 md:p-6 lg:p-8">{children}</div>
          </main>
          <VoiceCommand />
        </div>
      </body>
    </html>
  );
}
