import type { Metadata } from "next";
import "./globals.css";

/* eslint-disable @next/next/no-page-custom-font */

export const metadata: Metadata = {
  title: "Диктум - локальная расшифровка длинных записей на Mac",
  description:
    "Диктум превращает длинные диктофонные записи в точные протоколы по спикерам на вашем Mac: локально, приватно и без обязательной подписки.",
  keywords: [
    "Диктум",
    "расшифровка аудио",
    "транскрибация на Mac",
    "диаризация",
    "локальная транскрибация",
    "распознавание русской речи",
  ],
  openGraph: {
    title: "Диктум - точные протоколы из длинных записей, локально на Mac",
    description:
      "Русская речь с пунктуацией, разделение спикеров и готовый протокол. На вашем Mac, без облака.",
    type: "website",
  },
  icons: {
    icon: "/favicon.svg",
    shortcut: "/favicon.svg",
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="ru">
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="" />
        <link
          href="https://fonts.googleapis.com/css2?family=Spectral:ital,wght@0,400;0,500;0,600;1,400&family=Golos+Text:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap"
          rel="stylesheet"
        />
      </head>
      <body>{children}</body>
    </html>
  );
}
