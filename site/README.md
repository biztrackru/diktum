# Диктум public site

Sites-compatible лендинг Диктум, собранный из локального макета
`docs/site/dictum-landing.dc.html`.

## Что внутри

- `app/DiktumLanding.tsx` - клиентский лендинг с RU/EN переключателем и email-gate.
- `app/api/leads/route.ts` - серверный прием email, D1 upsert, optional webhook и возврат download URL.
- `app/api/leads/export/route.ts` - CSV export до 500 последних лидов по секретному `LEADS_EXPORT_TOKEN`.
- `db/schema.ts` и `drizzle/` - D1 schema и migration для таблицы `leads`.
- `public/screenshots/` - очищенные скриншоты продукта из `docs/site/screenshots/`.

## Runtime env

Runtime значения задаются в Sites, не в Git:

```bash
DOWNLOAD_URL=https://github.com/biztrackru/diktum/releases/download/v0.1.0-alpha.1/diktum-v0.1.0-alpha.1-macos.zip
LEADS_EXPORT_TOKEN=<secret>
LEADS_WEBHOOK_URL=<optional secret https webhook>
LEADS_WEBHOOK_TOKEN=<optional bearer token>
```

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
```
