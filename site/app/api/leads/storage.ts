import { createHash } from "node:crypto";

export type LeadRecord = {
  email: string;
  source: string;
  locale: string;
  firstSeenAt: string;
  lastSeenAt: string;
  submitCount: number;
  notifiedAt?: string;
};

type FirestoreField = {
  integerValue?: string;
  stringValue?: string;
};

type FirestoreDocument = {
  fields?: Record<string, FirestoreField>;
};

const METADATA_TOKEN_URL =
  "http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/token";

function envValue(name: string) {
  return process.env[name]?.trim() ?? "";
}

function firestoreProjectId() {
  return (
    envValue("FIRESTORE_PROJECT_ID") ||
    envValue("GOOGLE_CLOUD_PROJECT") ||
    envValue("GCLOUD_PROJECT")
  );
}

function firestoreDatabaseId() {
  return envValue("FIRESTORE_DATABASE_ID") || "(default)";
}

function firestoreBaseUrl() {
  const projectId = firestoreProjectId();
  if (!projectId) {
    throw new Error("firestore-project-id-missing");
  }

  return `https://firestore.googleapis.com/v1/projects/${projectId}/databases/${encodeURIComponent(
    firestoreDatabaseId()
  )}/documents`;
}

function leadDocumentId(email: string) {
  return createHash("sha256").update(email).digest("hex");
}

async function accessToken() {
  const configuredToken = envValue("GOOGLE_OAUTH_ACCESS_TOKEN");
  if (configuredToken) return configuredToken;

  const response = await fetch(METADATA_TOKEN_URL, {
    headers: { "Metadata-Flavor": "Google" },
  });

  if (!response.ok) {
    throw new Error("metadata-token-unavailable");
  }

  const payload = (await response.json()) as { access_token?: string };
  if (!payload.access_token) {
    throw new Error("metadata-token-empty");
  }

  return payload.access_token;
}

async function firestoreFetch(path: string, init?: RequestInit) {
  const token = await accessToken();
  const response = await fetch(`${firestoreBaseUrl()}${path}`, {
    ...init,
    headers: {
      authorization: `Bearer ${token}`,
      "content-type": "application/json",
      ...(init?.headers ?? {}),
    },
  });

  return response;
}

function stringField(document: FirestoreDocument, name: string) {
  return document.fields?.[name]?.stringValue ?? "";
}

function integerField(document: FirestoreDocument, name: string) {
  const value = Number.parseInt(document.fields?.[name]?.integerValue ?? "", 10);
  return Number.isFinite(value) ? value : 0;
}

function documentToLead(document: FirestoreDocument): LeadRecord {
  return {
    email: stringField(document, "email"),
    source: stringField(document, "source") || "landing",
    locale: stringField(document, "locale") || "ru",
    firstSeenAt: stringField(document, "first_seen_at"),
    lastSeenAt: stringField(document, "last_seen_at"),
    submitCount: integerField(document, "submit_count") || 1,
    notifiedAt: stringField(document, "notified_at") || undefined,
  };
}

function leadToFirestoreFields(lead: LeadRecord) {
  const fields: Record<string, FirestoreField> = {
    email: { stringValue: lead.email },
    source: { stringValue: lead.source },
    locale: { stringValue: lead.locale },
    first_seen_at: { stringValue: lead.firstSeenAt },
    last_seen_at: { stringValue: lead.lastSeenAt },
    submit_count: { integerValue: String(lead.submitCount) },
  };

  if (lead.notifiedAt) {
    fields.notified_at = { stringValue: lead.notifiedAt };
  }

  return fields;
}

async function getLead(email: string) {
  const response = await firestoreFetch(`/leads/${leadDocumentId(email)}`);
  if (response.status === 404) return null;

  if (!response.ok) {
    throw new Error(`firestore-read-failed-${response.status}`);
  }

  return documentToLead((await response.json()) as FirestoreDocument);
}

export async function upsertLead(input: {
  email: string;
  source: string;
  locale: string;
  now: string;
}) {
  const existing = await getLead(input.email);
  const lead: LeadRecord = {
    email: input.email,
    source: input.source,
    locale: input.locale,
    firstSeenAt: existing?.firstSeenAt || input.now,
    lastSeenAt: input.now,
    submitCount: (existing?.submitCount ?? 0) + 1,
    notifiedAt: existing?.notifiedAt,
  };

  const response = await firestoreFetch(`/leads/${leadDocumentId(input.email)}`, {
    method: "PATCH",
    body: JSON.stringify({ fields: leadToFirestoreFields(lead) }),
  });

  if (!response.ok) {
    throw new Error(`firestore-write-failed-${response.status}`);
  }

  return lead;
}

export async function markLeadNotified(email: string, notifiedAt: string) {
  const existing = await getLead(email);
  if (!existing) return;

  const response = await firestoreFetch(`/leads/${leadDocumentId(email)}`, {
    method: "PATCH",
    body: JSON.stringify({
      fields: leadToFirestoreFields({ ...existing, notifiedAt }),
    }),
  });

  if (!response.ok) {
    throw new Error(`firestore-notify-update-failed-${response.status}`);
  }
}

export async function listLeads(limit = 500) {
  const response = await firestoreFetch(":runQuery", {
    method: "POST",
    body: JSON.stringify({
      structuredQuery: {
        from: [{ collectionId: "leads" }],
        orderBy: [
          {
            field: { fieldPath: "last_seen_at" },
            direction: "DESCENDING",
          },
        ],
        limit,
      },
    }),
  });

  if (!response.ok) {
    throw new Error(`firestore-query-failed-${response.status}`);
  }

  const rows = (await response.json()) as Array<{ document?: FirestoreDocument }>;
  return rows.flatMap((row) => (row.document ? [documentToLead(row.document)] : []));
}
