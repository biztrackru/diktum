import { listLeads } from "../storage";

type RuntimeEnv = {
  LEADS_EXPORT_TOKEN?: string;
};

function runtimeEnv() {
  return process.env as RuntimeEnv;
}

function csvCell(value: unknown) {
  const text = value == null ? "" : String(value);
  return `"${text.replace(/"/g, '""')}"`;
}

function bearerToken(request: Request) {
  const authorization = request.headers.get("authorization")?.trim() ?? "";
  const [scheme, ...parts] = authorization.split(/\s+/);

  if (scheme.toLowerCase() !== "bearer") {
    return "";
  }

  return parts.join(" ").trim();
}

export async function GET(request: Request) {
  const configuredToken = runtimeEnv().LEADS_EXPORT_TOKEN?.trim();
  const requestToken = bearerToken(request);

  if (!configuredToken || requestToken !== configuredToken) {
    return Response.json(
      { error: "not-found" },
      {
        status: 404,
        headers: { "cache-control": "no-store" },
      }
    );
  }

  const rows = await listLeads(500);

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
