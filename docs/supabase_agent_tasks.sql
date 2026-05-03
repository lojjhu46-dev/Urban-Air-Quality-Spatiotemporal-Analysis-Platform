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
