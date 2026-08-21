import "./globals.css";

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="en"><body><main className="mx-auto max-w-5xl p-6">{children}</main></body></html>;
}
