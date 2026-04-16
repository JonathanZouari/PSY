-- ============================================================
-- ניתוח שיחות — initial schema
-- Tables, RLS policies, and storage bucket for the call-analysis app.
-- ============================================================

-- ---------- Tables ----------

create table if not exists public.recordings (
  id                uuid primary key default gen_random_uuid(),
  user_id           uuid not null references auth.users(id) on delete cascade,
  created_at        timestamptz not null default now(),
  duration_seconds  int,
  audio_path        text not null,
  status            text not null default 'pending'
                      check (status in ('pending','transcribing','analyzing','done','failed')),
  error_message     text
);

create index if not exists recordings_user_created_idx
  on public.recordings (user_id, created_at desc);

create table if not exists public.analyses (
  id                       uuid primary key default gen_random_uuid(),
  recording_id             uuid not null unique references public.recordings(id) on delete cascade,
  transcript               text not null,
  summary                  text,
  key_points               jsonb,
  topics                   jsonb,
  tasks                    jsonb,
  sentiment                text check (sentiment in ('positive','negative','neutral','mixed')),
  sentiment_explanation    text,
  entities                 jsonb,
  created_at               timestamptz not null default now()
);

-- ---------- Row Level Security on app tables ----------
-- Backend uses the service-role key which bypasses RLS; these policies are
-- defense-in-depth in case the anon key is ever used directly from a client.

alter table public.recordings enable row level security;
alter table public.analyses   enable row level security;

drop policy if exists "own recordings select" on public.recordings;
create policy "own recordings select" on public.recordings
  for select using (auth.uid() = user_id);

drop policy if exists "own recordings insert" on public.recordings;
create policy "own recordings insert" on public.recordings
  for insert with check (auth.uid() = user_id);

-- UPDATE in Postgres RLS requires both USING (for the SELECT step) and
-- WITH CHECK (for the new row). Without WITH CHECK, the new row's user_id
-- could be changed silently.
drop policy if exists "own recordings update" on public.recordings;
create policy "own recordings update" on public.recordings
  for update using (auth.uid() = user_id) with check (auth.uid() = user_id);

drop policy if exists "own analyses select" on public.analyses;
create policy "own analyses select" on public.analyses
  for select using (
    exists (
      select 1 from public.recordings r
      where r.id = recording_id and r.user_id = auth.uid()
    )
  );

-- ---------- Storage: private "recordings" bucket ----------
-- Backend writes/reads via service-role key; clients only see signed URLs
-- minted by the backend. No public access; no anon/authenticated policies
-- needed (RLS denies by default).

insert into storage.buckets (id, name, public)
  values ('recordings', 'recordings', false)
  on conflict (id) do nothing;
