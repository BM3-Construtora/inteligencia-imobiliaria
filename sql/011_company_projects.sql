-- 011_company_projects.sql — Track company's own construction projects

CREATE TABLE IF NOT EXISTS company_projects (
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name            TEXT NOT NULL,
    land_listing_id BIGINT REFERENCES listings(id),
    neighborhood    TEXT,
    project_type    TEXT NOT NULL,       -- 'mcmv_faixa1', 'mcmv_faixa2', 'casa_padrao'
    units           INT NOT NULL DEFAULT 1,
    land_cost       NUMERIC(14,2),
    construction_cost_projected NUMERIC(14,2),
    construction_cost_actual    NUMERIC(14,2),
    revenue_projected NUMERIC(14,2),
    revenue_actual    NUMERIC(14,2),
    margin_projected_pct NUMERIC(5,2),
    margin_actual_pct    NUMERIC(5,2),
    status          TEXT NOT NULL DEFAULT 'planning',  -- planning, approved, construction, selling, sold_out, cancelled
    started_at      DATE,
    completed_at    DATE,
    notes           TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE company_projects ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Public read company_projects" ON company_projects FOR SELECT USING (true);
