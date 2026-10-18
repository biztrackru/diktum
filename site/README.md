# Диктум public site

Sites-compatible лендинг Диктум, собранный из локального макета
`docs/site/dictum-landing.dc.html`.

## Что внутри

- `app/DiktumLanding.tsx` - клиентский лендинг с RU/EN переключателем и email-gate.
- `app/api/leads/route.ts` - серверный прием email, Firestore upsert, optional webhook и возврат download URL.
- `app/api/leads/export/route.ts` - CSV export до 500 последних лидов по `Authorization: Bearer <LEADS_EXPORT_TOKEN>`.
- `db/schema.ts` и `drizzle/` - legacy D1 schema для Sites-сборки.
- `public/screenshots/` - очищенные скриншоты продукта из `docs/site/screenshots/`.

## Runtime env

Runtime значения задаются в Cloud Run или Sites, не в Git:

```bash
DOWNLOAD_URL=https://github.com/biztrackru/diktum/releases/download/v0.2.0-alpha.2/diktum-v0.2.0-alpha.2-macos.zip
FIRESTORE_PROJECT_ID=vostorg-production-2026-0806
FIRESTORE_DATABASE_ID=(default)
LEADS_EXPORT_TOKEN=<secret>
LEADS_WEBHOOK_URL=<optional secret https webhook>
LEADS_WEBHOOK_TOKEN=<optional bearer token>
```

Для Cloud Run `LEADS_EXPORT_TOKEN` хранится в Secret Manager, а лиды пишутся в
Firestore database `(default)`.

Если `LEADS_WEBHOOK_URL` задан, endpoint получает JSON:

```json
{
  "product": "Диктум",
  "email": "person@example.com",
  "locale": "ru",
  "source": "landing-modal",
  "createdAt": "2026-06-30T00:00:00.000Z"
}
```

## Checks

```bash
npm ci
npm run db:generate
npm run lint
npm run build
npm run build:gcp
```

## Cloud Run

Контейнерная сборка использует `Dockerfile` и стандартный Next standalone
server. Для загрузки source в Cloud Build используется `.gcloudignore`, чтобы
не отправлять локальные `.env`, `.next`, `.wrangler`, `dist` и `node_modules`.

## Компоненты сборки после обновления 19 октября 2026

Cloud Run использует Next.js 16.4.2 и React 19.3.1. Dockerfile закрепляет
`node:22-slim` по digest. `build:gcp` явно выбирает поддерживаемый webpack:
Turbopack в ограниченном локальном окружении может не получить разрешение
на внутренний CSS IPC socket. Vinext 1.2.1 и Vite 8.3.4 обслуживают второй путь.

`npm run typecheck` сначала запускает `next typegen`, потому что vinext и Next
создают разные версии route types в `.next/types`. После сборки vinext повторная
проверка типов сначала восстанавливает типы Next. Сгенерированные файлы не коммитятся.

TypeScript 6.0.3 и ESLint 9.39.5 выбраны по совместимости с текущими плагинами
Next. TypeScript 7 и ESLint 10 пока конфликтуют с их peer dependencies.
Точечные overrides закрывают найденные advisory в транзитивных пакетах;
`npm audit fix --force` применять без отдельной проверки не следует.

Production-аудит проверяется отдельно: `npm audit --omit=dev`. После обновления
он не сообщает уязвимостей. В полном dev-дереве остаются advisory по Babel 7
и цепочкам `braces` через glob/vinext/ESLint; старые инструменты нельзя открывать
как публичный dev server или использовать для обработки недоверенных glob/source map.
Результаты относятся к локальному lock; облачная ревизия обновляется отдельно.
