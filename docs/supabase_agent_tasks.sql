create table if not exists agent_tasks (
    task_id text primary key,
    kind text not null,
    status text not null,
    phase text not null,
    progress double precision not null default 0,
    message text not null default '',
    request_payload jsonb not null default '{}'::jsonb,
    result_payload jsonb not null default '{}'::jsonb,
    error text,
    output_path text,
    created_at timestamptz not null,
    updated_at timestamptz not null,
    started_at timestamptz,
    finished_at timestamptz
);

create table if not exists agent_task_logs (
    id bigserial primary key,
    task_id text not null references agent_tasks(task_id) on delete cascade,
    level text not null,
    phase text not null,
    message text not null,
    created_at timestamptz not null
);

create index if not exists idx_agent_task_logs_task_created
    on agent_task_logs(task_id, created_at);

create table if not exists dataset_index (
    id bigserial primary key,
    city text not null default '',
    country_code text not null default '',
    start_date text not null default '',
    end_date text not null default '',
    pollutants jsonb not null default '[]'::jsonb,
    row_count integer not null default 0,
    format text not null default 'parquet',
    storage_uri text not null,
    source_task_id text,
    created_at timestamptz not null default now(),
    constraint dataset_index_storage_uri_unique unique (storage_uri)
);

create index if not exists idx_dataset_index_city
    on dataset_index(city, country_code);

create index if not exists idx_dataset_index_created
    on dataset_index(created_at desc);
