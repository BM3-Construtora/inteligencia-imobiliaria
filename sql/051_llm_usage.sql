-- 051_llm_usage.sql — Telemetria de custo de LLM (Gemini)
-- Registra tokens e custo estimado por chamada, para saber o gasto real
-- e priorizar otimização com dados (não chute).

CREATE TABLE IF NOT EXISTS llm_usage (
    id              BIGSERIAL PRIMARY KEY,
    ts              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    model           TEXT NOT NULL,              -- ex: 'gemini-2.5-flash'
    task            TEXT NOT NULL,              -- ex: 'extract_attributes', 'assess_risk', 'vision'
    llm_mode        TEXT,                       -- 'ai_studio' | 'vertex_ai'
    prompt_tokens   INTEGER NOT NULL DEFAULT 0,
    output_tokens   INTEGER NOT NULL DEFAULT 0, -- candidates (resposta)
    thinking_tokens INTEGER NOT NULL DEFAULT 0, -- reasoning tokens (cobrados como output no 2.5)
    total_tokens    INTEGER NOT NULL DEFAULT 0,
    est_cost_usd    NUMERIC NOT NULL DEFAULT 0, -- custo estimado pela tabela de preços em src/llm_usage.py
    run_id          BIGINT,                     -- opcional: agent_runs.id
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_llm_usage_ts    ON llm_usage (ts DESC);
CREATE INDEX IF NOT EXISTS idx_llm_usage_model ON llm_usage (model);
CREATE INDEX IF NOT EXISTS idx_llm_usage_task  ON llm_usage (task);

ALTER TABLE llm_usage ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "service_role full access on llm_usage" ON llm_usage;
CREATE POLICY "service_role full access on llm_usage"
    ON llm_usage FOR ALL TO service_role USING (true) WITH CHECK (true);

-- Agregação mensal pronta para consulta: custo por modelo e tarefa
CREATE OR REPLACE VIEW llm_usage_monthly AS
SELECT
    date_trunc('month', ts)      AS mes,
    model,
    task,
    COUNT(*)                     AS calls,
    SUM(prompt_tokens)           AS prompt_tokens,
    SUM(output_tokens)           AS output_tokens,
    SUM(thinking_tokens)         AS thinking_tokens,
    SUM(total_tokens)            AS total_tokens,
    ROUND(SUM(est_cost_usd), 4)  AS est_cost_usd
FROM llm_usage
GROUP BY date_trunc('month', ts), model, task
ORDER BY mes DESC, est_cost_usd DESC;
