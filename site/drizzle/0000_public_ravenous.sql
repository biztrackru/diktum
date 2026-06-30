CREATE TABLE `leads` (
	`id` integer PRIMARY KEY AUTOINCREMENT NOT NULL,
	`email` text NOT NULL,
	`source` text DEFAULT 'landing' NOT NULL,
	`locale` text DEFAULT 'ru' NOT NULL,
	`first_seen_at` text NOT NULL,
	`last_seen_at` text NOT NULL,
	`submit_count` integer DEFAULT 1 NOT NULL,
	`notified_at` text
);
--> statement-breakpoint
CREATE UNIQUE INDEX `leads_email_unique` ON `leads` (`email`);--> statement-breakpoint
CREATE INDEX `leads_last_seen_email_idx` ON `leads` (`last_seen_at`,`email`);