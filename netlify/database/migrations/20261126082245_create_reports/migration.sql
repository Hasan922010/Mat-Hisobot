CREATE TABLE "report_batch" (
	"id" uuid PRIMARY KEY DEFAULT gen_random_uuid(),
	"owner" text NOT NULL,
	"company" text NOT NULL,
	"stir" text NOT NULL,
	"year" integer NOT NULL,
	"period" text NOT NULL,
	"files" jsonb NOT NULL,
	"options" jsonb NOT NULL,
	"status" text DEFAULT 'DRAFT' NOT NULL,
	"summary" jsonb,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL,
	"started_at" timestamp with time zone
);
--> statement-breakpoint
CREATE TABLE "report_row" (
	"batch_id" uuid,
	"row_group" text,
	"position" integer,
	"search_text" text NOT NULL,
	"data" jsonb NOT NULL,
	CONSTRAINT "report_row_pkey" PRIMARY KEY("batch_id","row_group","position")
);
--> statement-breakpoint
CREATE INDEX "report_batch_owner_created_idx" ON "report_batch" ("owner","created_at");--> statement-breakpoint
ALTER TABLE "report_row" ADD CONSTRAINT "report_row_batch_id_report_batch_id_fkey" FOREIGN KEY ("batch_id") REFERENCES "report_batch"("id") ON DELETE CASCADE;