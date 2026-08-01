import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "多模态农田孢子监测与病害扩散预警系统 V4.0",
  description: "软著桌面程序的本地 Web 控制台功能复现版。",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="zh-CN">
      <body>{children}</body>
    </html>
  );
}
