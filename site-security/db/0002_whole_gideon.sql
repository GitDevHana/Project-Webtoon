CREATE TABLE `security_events` (
	`id` text PRIMARY KEY NOT NULL,
	`actor_id` text,
	`action` text NOT NULL,
	`resource` text NOT NULL,
	`status` integer NOT NULL,
	`occurred_at` integer NOT NULL
);
--> statement-breakpoint
CREATE INDEX `security_events_time_idx` ON `security_events` (`occurred_at`);--> statement-breakpoint
CREATE TABLE `security_limits` (
	`key` text PRIMARY KEY NOT NULL,
	`window_start` integer NOT NULL,
	`count` integer NOT NULL
);
