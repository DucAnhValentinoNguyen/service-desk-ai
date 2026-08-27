import "./globals.css";

export const metadata = {
  title: "Service Desk AI",
  description: "Guarded operations copilot for ERP, CRM, HRM, and appointments",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return <html lang="en"><body>{children}</body></html>;
}
