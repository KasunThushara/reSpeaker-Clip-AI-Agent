-- Vector Search stage schema — run this in the Supabase SQL Editor once.
create table if not exists public.users (
  id text primary key,
  email text unique,
  created_at timestamptz not null default now()
);

create table if not exists public.conversations (
  id text primary key,
  user_id text references public.users(id),
  title text,
  overview text,
  action_items text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.messages (
  id bigint generated always as identity primary key,
  conversation_id text references public.conversations(id) on delete cascade,
  role text not null,
  content text not null,
  created_at timestamptz not null default now()
);

insert into public.users (id, email) values ('user-1', 'user-1@local')
on conflict (id) do nothing;

-- Clip ingestion workflow state (keyed by device_id + session_id).
create table if not exists public.clip_ingestions (
  device_id text not null,
  session_id text not null,
  trigger text,
  source text,
  conversation_id text references public.conversations(id),
  status text not null default 'stopped',
  transcript text,
  response text,
  error text,
  metadata jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  primary key (device_id, session_id)
);

-- Persist the one-time baseline independently of session rows. This prevents
-- every application restart from treating newly recorded sessions as history.
create table if not exists public.clip_device_state (
  device_id text primary key,
  baseline_completed boolean not null default false,
  updated_at timestamptz not null default now()
);
