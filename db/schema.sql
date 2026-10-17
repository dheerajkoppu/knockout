-- Knockout store on Tiger Data (TimescaleDB on PostgreSQL). Safe to run again: every statement is idempotent.

create extension if not exists timescaledb;

create table if not exists drugs (
    name text primary key check (name <> '' and name = lower(name)),
    chembl_id text,
    display_name text,
    max_phase numeric,
    molecule_type text,
    url text,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

-- The latest engine Report per drug, exactly as the API serves it.
create table if not exists reports (
    drug text primary key references drugs (name) on delete cascade,
    report jsonb not null,
    generated_at timestamptz,
    cached_at timestamptz not null default now()
);

create table if not exists predictions (
    id bigint generated always as identity primary key,
    drug text not null references drugs (name) on delete cascade,
    position integer not null,
    hpo_id text not null,
    phenotype text not null,
    frequency text,
    kind text,
    gene text not null,
    target text not null,
    disease_id text not null,
    disease text not null,
    reaction_terms text[] not null default '{}',
    label_section text,
    label_term text,
    label_sentence text,
    counts jsonb not null default '[]',
    verdict text not null check (verdict in ('on_label', 'signal_in_reports', 'no_signal', 'unknown')),
    reason text,
    candidate_new_signal boolean not null default false,
    generated_at timestamptz,
    unique (drug, position)
);

-- One row per cited record: ChEMBL mechanism, catalog provenance, direction source, phenotype, label sentence.
create table if not exists evidence (
    id bigint generated always as identity primary key,
    prediction_id bigint not null references predictions (id) on delete cascade,
    position integer not null,
    source text not null check (btrim(source) <> ''),
    description text not null,
    url text,
    unique (prediction_id, position)
);

create index if not exists evidence_by_source on evidence (source);
create index if not exists predictions_by_verdict on predictions (verdict, drug);

create table if not exists watchlist (
    drug text primary key references drugs (name) on delete cascade,
    added_at timestamptz not null default now()
);

-- One row per watch-agent run per drug; the previous run is the one an alert is measured against.
create table if not exists signal_runs (
    drug text not null references drugs (name) on delete cascade,
    run_id text not null check (btrim(run_id) <> ''),
    run_at timestamptz not null,
    received_at timestamptz not null default now(),
    terms integer not null default 0,
    primary key (drug, run_id)
);

create index if not exists signal_runs_by_time on signal_runs (drug, run_at desc);

-- 'manual' when a person chose the terms (watch.py --term) rather than the report's mapping.
alter table signal_runs add column if not exists term_source text not null default 'report'
    check (term_source in ('report', 'manual'));

create table if not exists faers_counts (
    quarter date not null check (quarter = date_trunc('quarter', quarter)::date),
    drug text not null,
    term text not null,
    reports integer not null check (reports >= 0),
    prr double precision,
    signal boolean not null,
    run_id text not null,
    run_at timestamptz not null,
    foreign key (drug, run_id) references signal_runs (drug, run_id) on delete cascade,
    unique (drug, term, run_id, quarter)
);

select create_hypertable('faers_counts', by_range('quarter', interval '5 years'), if_not_exists => true);

create index if not exists faers_counts_by_run on faers_counts (drug, run_id, term, quarter desc);

-- Old quarters rarely change, so they move to the columnstore; late recounts still upsert into them.
do $$
begin
    if not exists (
        select 1 from timescaledb_information.hypertables
        where hypertable_schema = current_schema() and hypertable_name = 'faers_counts' and compression_enabled
    ) then
        alter table faers_counts set (
            timescaledb.compress,
            timescaledb.compress_segmentby = 'drug, term',
            timescaledb.compress_orderby = 'quarter desc, run_id'
        );
    end if;
end $$;

select add_compression_policy('faers_counts', compress_after => interval '6 years', if_not_exists => true);

create table if not exists alerts (
    id bigint generated always as identity primary key,
    drug text not null references drugs (name) on delete cascade,
    term text not null,
    quarter date not null,
    prr double precision,
    run_id text not null,
    previous_run_id text not null,
    crossed_at timestamptz not null,
    foreign key (drug, run_id) references signal_runs (drug, run_id) on delete cascade,
    unique (drug, term, run_id)
);

create index if not exists alerts_by_drug on alerts (drug, crossed_at desc);

-- The trend chart: per drug, term and quarter, the count from the latest run that measured that quarter.
create materialized view if not exists faers_trend
with (timescaledb.continuous, timescaledb.materialized_only = false) as
select
    drug,
    term,
    time_bucket(interval '3 months', quarter) as quarter,
    last(reports, run_at) as reports,
    last(prr, run_at) as prr,
    last(signal, run_at) as signal,
    max(run_at) as last_run_at,
    count(*) as runs
from faers_counts
group by drug, term, time_bucket(interval '3 months', quarter)
with no data;

select add_continuous_aggregate_policy(
    'faers_trend',
    start_offset => null,
    end_offset => null,
    schedule_interval => interval '1 hour',
    if_not_exists => true
);

-- No prediction without its cited chain: checked at commit, so a prediction and its evidence go in together.
create or replace function knockout_prediction_needs_evidence() returns trigger
language plpgsql
set search_path from current
as $$
begin
    if exists (select 1 from predictions where id = new.id)
       and not exists (select 1 from evidence where prediction_id = new.id) then
        raise exception using
            errcode = 'integrity_constraint_violation',
            message = format(
                'prediction %s (%s %s, from %s) for %s has no evidence row',
                new.id, new.hpo_id, new.phenotype, new.disease, new.drug
            ),
            hint = 'No prediction without its cited chain: insert its evidence in the same transaction.';
    end if;
    return null;
end
$$;

drop trigger if exists predictions_need_evidence on predictions;
create constraint trigger predictions_need_evidence
    after insert or update on predictions
    deferrable initially deferred
    for each row execute function knockout_prediction_needs_evidence();

-- The same rule from the other side: evidence cannot be removed from a prediction that stays.
create or replace function knockout_evidence_keeps_chain() returns trigger
language plpgsql
set search_path from current
as $$
begin
    if exists (select 1 from predictions where id = old.prediction_id)
       and not exists (select 1 from evidence where prediction_id = old.prediction_id) then
        raise exception using
            errcode = 'integrity_constraint_violation',
            message = format('removing evidence left prediction %s with no evidence row', old.prediction_id),
            hint = 'No prediction without its cited chain: delete the prediction, or keep at least one record.';
    end if;
    return null;
end
$$;

drop trigger if exists evidence_keeps_chain on evidence;
create constraint trigger evidence_keeps_chain
    after delete or update of prediction_id on evidence
    deferrable initially deferred
    for each row execute function knockout_evidence_keeps_chain();
