-- Remove unused embedding column (vector(1536), never populated, custo storage zero ganho).
-- Se reativar embeddings depois, recriar com vector(768) suficiente p/ multilingual-e5.

ALTER TABLE listings DROP COLUMN IF EXISTS embedding;
-- Extension vector continua habilitada (barato), facilita recriação futura.
