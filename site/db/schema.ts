import { index, integer, sqliteTable, text, uniqueIndex } from "drizzle-orm/sqlite-core";

export const leads = sqliteTable(
  "leads",
  {
    id: integer("id").primaryKey({ autoIncrement: true }),
    email: text("email").notNull(),
    source: text("source").notNull().default("landing"),
    locale: text("locale").notNull().default("ru"),
    firstSeenAt: text("first_seen_at").notNull(),
    lastSeenAt: text("last_seen_at").notNull(),
    submitCount: integer("submit_count").notNull().default(1),
    notifiedAt: text("notified_at"),
  },
  (table) => [
    uniqueIndex("leads_email_unique").on(table.email),
    index("leads_last_seen_email_idx").on(table.lastSeenAt, table.email),
  ]
);
