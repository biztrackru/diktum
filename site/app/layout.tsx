import type { Metadata } from "next";
import "./globals.css";

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
      <body>{children}</body>
    </html>
  );
}
