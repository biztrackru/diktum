import { env } from "cloudflare:workers";
import { eq, sql } from "drizzle-orm";
import { getDb } from "@/db";
import { leads } from "@/db/schema";

const DEFAULT_DOWNLOAD_URL =
  "https://github.com/biztrackru/diktum/releases/download/v0.1.0-alpha.1/diktum-v0.1.0-alpha.1-macos.zip";

const EMAIL_RE = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;

type RuntimeEnv = {
  DB?: D1Database;
  DOWNLOAD_URL?: string;
  LEADS_EXPORT_TOKEN?: string;
  LEADS_WEBHOOK_TOKEN?: string;
  LEADS_WEBHOOK_URL?: string;
};

type LeadPayload = {
  company?: string;
  email?: string;
  locale?: string;
  source?: string;
};

function runtimeEnv() {
  return env as unknown as RuntimeEnv;
}

function json(body: unknown, init?: ResponseInit) {
  return Response.json(body, {
    ...init,
    headers: {
      "cache-control": "no-store",
      ...(init?.headers ?? {}),
    },
  });
}

function cleanText(value: unknown, fallback: string, max = 80) {
  if (typeof value !== "string") return fallback;
  const cleaned = value.trim().replace(/\s+/g, " ");
  return cleaned ? cleaned.slice(0, max) : fallback;
}

function downloadUrl() {
  const configured = runtimeEnv().DOWNLOAD_URL?.trim();
  if (configured && configured.startsWith("https://")) return configured;
  return DEFAULT_DOWNLOAD_URL;
}

async function ensureLeadSchema() {
  const db = runtimeEnv().DB;
  if (!db) return;

  await db.batch([
    db.prepare(
      "CREATE TABLE IF NOT EXISTS leads (id integer PRIMARY KEY AUTOINCREMENT NOT NULL, email text NOT NULL, source text DEFAULT 'landing' NOT NULL, locale text DEFAULT 'ru' NOT NULL, first_seen_at text NOT NULL, last_seen_at text NOT NULL, submit_count integer DEFAULT 1 NOT NULL, notified_at text)"
    ),
    db.prepare("CREATE UNIQUE INDEX IF NOT EXISTS leads_email_unique ON leads (email)"),
    db.prepare("CREATE INDEX IF NOT EXISTS leads_last_seen_email_idx ON leads (last_seen_at, email)"),
  ]);
}

async function forwardLead(email: string, locale: string, source: string) {
  const webhookUrl = runtimeEnv().LEADS_WEBHOOK_URL?.trim();
  if (!webhookUrl || !webhookUrl.startsWith("https://")) return false;

  const headers = new Headers({ "content-type": "application/json" });
  const token = runtimeEnv().LEADS_WEBHOOK_TOKEN?.trim();
  if (token) headers.set("authorization", `Bearer ${token}`);

  const response = await fetch(webhookUrl, {
    method: "POST",
    headers,
    body: JSON.stringify({
      product: "Диктум",
      email,
      locale,
      source,
      createdAt: new Date().toISOString(),
    }),
  });

  return response.ok;
}

export async function GET() {
  return json({ ok: true });
}

export async function POST(request: Request) {
  let payload: LeadPayload;

  try {
    payload = (await request.json()) as LeadPayload;
  } catch {
    return json({ error: "invalid-json" }, { status: 400 });
  }

  const normalizedEmail = payload.email?.trim().toLowerCase() ?? "";
  const source = cleanText(payload.source, "landing");
  const locale = cleanText(payload.locale, "ru", 12);

  if (payload.company) {
    return json({ ok: true, downloadUrl: downloadUrl() });
  }

  if (!EMAIL_RE.test(normalizedEmail)) {
    return json({ error: "invalid-email" }, { status: 400 });
  }

  const now = new Date().toISOString();

  try {
    await ensureLeadSchema();
    const db = getDb();

    await db
      .insert(leads)
      .values({
        email: normalizedEmail,
        source,
        locale,
        firstSeenAt: now,
        lastSeenAt: now,
      })
      .onConflictDoUpdate({
        target: leads.email,
        set: {
          source,
          locale,
          lastSeenAt: now,
          submitCount: sql`${leads.submitCount} + 1`,
        },
      })
      .run();

    const notified = await forwardLead(normalizedEmail, locale, source).catch(() => false);

    if (notified) {
      await db
        .update(leads)
        .set({ notifiedAt: new Date().toISOString() })
        .where(eq(leads.email, normalizedEmail))
        .run();
    }

    return json({ ok: true, downloadUrl: downloadUrl() }, { status: 201 });
  } catch (error) {
    const message = error instanceof Error ? error.message : "lead-save-failed";
    return json({ error: message }, { status: 500 });
  }
}
