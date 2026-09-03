-- Safety indexes for the episode and run identifiers used by the pipeline.
-- Apply after 001_cs_slice1_schema.sql.

create unique index if not exists cs_episodes_ep_number_unique
  on cs_episodes (ep_number)
  where ep_number is not null;

create unique index if not exists cs_runs_dag_run_unique
  on cs_runs (dag_id, airflow_run_id);

create index if not exists cs_episodes_status_created_at_idx
  on cs_episodes (status, created_at desc);
