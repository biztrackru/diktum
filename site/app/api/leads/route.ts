import { markLeadNotified, upsertLead } from "./storage";

const DEFAULT_DOWNLOAD_URL =
  "https://github.com/biztrackru/diktum/releases/download/v0.1.0-alpha.1/diktum-v0.1.0-alpha.1-macos.zip";

const EMAIL_RE = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;

type RuntimeEnv = {
  DOWNLOAD_URL?: string;
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
  return process.env as RuntimeEnv;
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
    await upsertLead({ email: normalizedEmail, source, locale, now });
    const notified = await forwardLead(normalizedEmail, locale, source).catch(() => false);

    if (notified) {
      await markLeadNotified(normalizedEmail, new Date().toISOString());
    }

    return json({ ok: true, downloadUrl: downloadUrl() }, { status: 201 });
  } catch (error) {
    const message = error instanceof Error ? error.message : "lead-save-failed";
    return json({ error: message }, { status: 500 });
  }
}
