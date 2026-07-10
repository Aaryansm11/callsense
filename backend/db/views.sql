-- CallSense rollup views (rubric §8.4).
--
-- Averaging choice, defended: advisor = mean of that advisor's call composites;
-- team = mean OVER ADVISORS (not over calls, so one high-volume advisor can't
-- dominate the team number); org = mean over teams. Kept as plain views so they
-- are always consistent with the underlying scores and cost nothing at this
-- scale. Materialise past ~1M calls/quarter (documented, not built).
--
-- Migration 0002_rollup_views executes this file; it is the source of truth for
-- the view DDL.

-- Advisor rollup: mean of this advisor's per-call composites. Flags are counted
-- in a separate correlated subquery to avoid the join fan-out that would inflate
-- AVG(composite) when a call has multiple flags.
CREATE OR REPLACE VIEW v_advisor_scores AS
SELECT
    a.id                          AS advisor_id,
    a.team_id                     AS team_id,
    t.org_id                      AS org_id,
    a.name                        AS advisor_name,
    COUNT(cs.call_id)             AS scored_calls,
    AVG(cs.composite)             AS avg_composite,
    (
        SELECT COUNT(*)
        FROM flags f
        JOIN calls c2 ON c2.id = f.call_id
        WHERE c2.advisor_id = a.id
          AND f.severity = 'critical'
    )                             AS critical_flags
FROM advisors a
JOIN teams t              ON t.id = a.team_id
LEFT JOIN calls c         ON c.advisor_id = a.id
LEFT JOIN call_scores cs  ON cs.call_id = c.id
GROUP BY a.id, a.team_id, t.org_id, a.name;

-- Team rollup: mean over advisor averages (NULLs — advisors with no scored
-- calls — are ignored by AVG, which is the intended "mean over active advisors").
CREATE OR REPLACE VIEW v_team_scores AS
SELECT
    t.id                                                    AS team_id,
    t.org_id                                                AS org_id,
    t.name                                                  AS team_name,
    COUNT(vs.advisor_id) FILTER (WHERE vs.scored_calls > 0) AS active_advisors,
    AVG(vs.avg_composite)                                   AS avg_composite,
    COALESCE(SUM(vs.critical_flags), 0)                     AS critical_flags
FROM teams t
LEFT JOIN v_advisor_scores vs ON vs.team_id = t.id
GROUP BY t.id, t.org_id, t.name;

-- Org rollup: mean over team averages.
CREATE OR REPLACE VIEW v_org_scores AS
SELECT
    o.id                                                      AS org_id,
    o.name                                                    AS org_name,
    COUNT(vt.team_id) FILTER (WHERE vt.avg_composite IS NOT NULL) AS active_teams,
    AVG(vt.avg_composite)                                     AS avg_composite,
    COALESCE(SUM(vt.critical_flags), 0)                       AS critical_flags
FROM orgs o
LEFT JOIN v_team_scores vt ON vt.org_id = o.id
GROUP BY o.id, o.name;
