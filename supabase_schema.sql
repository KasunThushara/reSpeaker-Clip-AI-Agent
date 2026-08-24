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
