import { env } from "cloudflare:workers";
import { desc } from "drizzle-orm";
import { getDb } from "@/db";
import { leads } from "@/db/schema";

type RuntimeEnv = {
  LEADS_EXPORT_TOKEN?: string;
};

function runtimeEnv() {
  return env as unknown as RuntimeEnv;
}

function csvCell(value: unknown) {
  const text = value == null ? "" : String(value);
  return `"${text.replace(/"/g, '""')}"`;
}

export async function GET(request: Request) {
  const configuredToken = runtimeEnv().LEADS_EXPORT_TOKEN?.trim();
  const requestToken = new URL(request.url).searchParams.get("token")?.trim();

  if (!configuredToken || requestToken !== configuredToken) {
    return Response.json(
      { error: "not-found" },
      {
        status: 404,
        headers: { "cache-control": "no-store" },
      }
    );
  }

  const rows = await getDb()
    .select()
    .from(leads)
    .orderBy(desc(leads.lastSeenAt))
    .limit(500)
    .all();

  const header = [
    "email",
    "source",
    "locale",
    "first_seen_at",
    "last_seen_at",
    "submit_count",
    "notified_at",
  ];
  const body = rows.map((row) =>
    [
      row.email,
      row.source,
      row.locale,
      row.firstSeenAt,
      row.lastSeenAt,
      row.submitCount,
      row.notifiedAt,
    ]
      .map(csvCell)
      .join(",")
  );

  return new Response([header.join(","), ...body].join("\n"), {
    headers: {
      "cache-control": "no-store",
      "content-disposition": "attachment; filename=diktum-leads.csv",
      "content-type": "text/csv; charset=utf-8",
    },
  });
}
