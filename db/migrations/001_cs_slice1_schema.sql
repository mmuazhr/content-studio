-- Applied to Supabase project tnihiqloksizyzillzxt as migration `cs_slice1_schema` on 2026-07-26.
-- Version-controlled copy; source of truth is the applied migration.

create type cs_episode_status as enum ('proposed','pending_script_review','script_approved','rejected','backlog','generating','pending_video_review','video_approved','posted','archived','error');
create type cs_episode_type as enum ('explainer','intro','promo');
create type cs_gate as enum ('script','video','promo');
create type cs_decision as enum ('approved','rejected','edited_then_approved');

create table cs_episodes (
  id uuid primary key default gen_random_uuid(),
  ep_number int,
  title text not null,
  topic_summary text not null default '',
  episode_type cs_episode_type not null default 'explainer',
  script jsonb not null default '[]',
  status cs_episode_status not null default 'proposed',
  rejection_note text,
  video_url text,
  caption text,
  local_path text,
  higgsfield_jobs jsonb not null default '{}',
  error_log text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table cs_approvals (
  id uuid primary key default gen_random_uuid(),
  episode_id uuid not null references cs_episodes(id),
  gate cs_gate not null,
  decision cs_decision not null,
  note text,
  decided_at timestamptz not null default now()
);

create table cs_runs (
  id uuid primary key default gen_random_uuid(),
  dag_id text not null,
  airflow_run_id text not null,
  episode_id uuid references cs_episodes(id),
  outcome text not null default 'running',
  credits_note text,
  started_at timestamptz not null default now(),
  finished_at timestamptz
);

-- Slice 2 TODO (flagged by Supabase advisor): ENABLE ROW LEVEL SECURITY + policies
-- on cs_episodes, cs_approvals, cs_runs before any non-localhost deployment.
