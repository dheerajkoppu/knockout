-- Shows the evidence trigger refusing a prediction with no cited chain. Changes nothing: both transactions end
-- in an error or a rollback. Run: psql "$DATABASE_URL" -f db/demo_trigger.sql

\set ON_ERROR_STOP off
\echo '1. A prediction inserted on its own fails at commit:'
begin;
insert into drugs (name) values ('trigger-demo') on conflict do nothing;
insert into predictions (drug, position, hpo_id, phenotype, gene, target, disease_id, disease, verdict)
values ('trigger-demo', 0, 'HP:0000001', 'Demo phenotype', 'DEMO', 'Demo protein', 'demo-disease', 'Demo disease',
        'unknown');
commit;

\echo '2. The same prediction with an evidence row in the same transaction is accepted (then rolled back):'
begin;
insert into drugs (name) values ('trigger-demo') on conflict do nothing;
with prediction as (
    insert into predictions (drug, position, hpo_id, phenotype, gene, target, disease_id, disease, verdict)
    values ('trigger-demo', 0, 'HP:0000001', 'Demo phenotype', 'DEMO', 'Demo protein', 'demo-disease',
            'Demo disease', 'unknown')
    returning id
)
insert into evidence (prediction_id, position, source, description)
select id, 0, 'chembl', 'Demo record' from prediction;
set constraints all immediate;
select count(*) as predictions_with_evidence from predictions where drug = 'trigger-demo';
rollback;
