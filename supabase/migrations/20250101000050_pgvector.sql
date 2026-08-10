-- 047_pgvector.sql — Reativa embeddings via pgvector (021_remove_embeddings.sql os removeu)
-- Usado para: busca semântica de imóveis similares, RAG de documentos municipais (CMDU, Plano Diretor)

CREATE EXTENSION IF NOT EXISTS vector;

-- Embeddings de listings (busca de similares, clustering de bairro)
CREATE TABLE IF NOT EXISTS listing_embeddings (
  id              BIGSERIAL PRIMARY KEY,
  listing_id      BIGINT NOT NULL REFERENCES listings(id) ON DELETE CASCADE,
  embedding       vector(768),       -- Gemini text-embedding-004 = 768 dims
  content_hash    TEXT,              -- SHA1 do texto que gerou o embedding
  model           TEXT DEFAULT 'text-embedding-004',
  embedded_at     TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE(listing_id)
);
CREATE INDEX IF NOT EXISTS idx_listing_emb_ivfflat
  ON listing_embeddings USING ivfflat (embedding vector_cosine_ops)
  WITH (lists = 100);

-- Embeddings de documentos municipais (CMDU atas, Plano Diretor, EIV pareceres)
CREATE TABLE IF NOT EXISTS document_embeddings (
  id              BIGSERIAL PRIMARY KEY,
  source_table    TEXT NOT NULL,     -- 'cmdu_atas', 'eiv_marilia', 'alvaras_marilia', 'plano_diretor'
  source_id       TEXT NOT NULL,     -- source_id da tabela de origem
  chunk_index     INTEGER DEFAULT 0, -- se o doc foi dividido em chunks
  chunk_text      TEXT NOT NULL,     -- texto do chunk (para exibição)
  embedding       vector(768),
  content_hash    TEXT,
  model           TEXT DEFAULT 'text-embedding-004',
  embedded_at     TIMESTAMPTZ DEFAULT NOW(),
  metadata        JSONB DEFAULT '{}'::jsonb,
  UNIQUE(source_table, source_id, chunk_index)
);
CREATE INDEX IF NOT EXISTS idx_doc_emb_ivfflat
  ON document_embeddings USING ivfflat (embedding vector_cosine_ops)
  WITH (lists = 50);
CREATE INDEX IF NOT EXISTS idx_doc_emb_source ON document_embeddings (source_table, source_id);

-- Função: buscar documentos similares a uma query
CREATE OR REPLACE FUNCTION search_documents(
  query_embedding vector(768),
  source_filter   TEXT DEFAULT NULL,   -- filtrar por source_table (ex: 'cmdu_atas')
  match_count     INTEGER DEFAULT 10,
  similarity_threshold FLOAT DEFAULT 0.7
)
RETURNS TABLE (
  source_table  TEXT,
  source_id     TEXT,
  chunk_index   INTEGER,
  chunk_text    TEXT,
  similarity    FLOAT,
  metadata      JSONB
)
LANGUAGE plpgsql AS $$
BEGIN
  RETURN QUERY
  SELECT
    de.source_table,
    de.source_id,
    de.chunk_index,
    de.chunk_text,
    1 - (de.embedding <=> query_embedding) AS similarity,
    de.metadata
  FROM document_embeddings de
  WHERE (source_filter IS NULL OR de.source_table = source_filter)
    AND 1 - (de.embedding <=> query_embedding) >= similarity_threshold
  ORDER BY de.embedding <=> query_embedding
  LIMIT match_count;
END;
$$;

-- Função: buscar listings similares a um listing de referência
CREATE OR REPLACE FUNCTION find_similar_listings(
  p_listing_id    BIGINT,
  match_count     INTEGER DEFAULT 5,
  similarity_threshold FLOAT DEFAULT 0.8
)
RETURNS TABLE (
  listing_id    BIGINT,
  similarity    FLOAT
)
LANGUAGE plpgsql AS $$
DECLARE
  ref_embedding vector(768);
BEGIN
  SELECT embedding INTO ref_embedding
  FROM listing_embeddings WHERE listing_id = p_listing_id;

  IF ref_embedding IS NULL THEN
    RETURN;
  END IF;

  RETURN QUERY
  SELECT
    le.listing_id,
    1 - (le.embedding <=> ref_embedding) AS similarity
  FROM listing_embeddings le
  WHERE le.listing_id != p_listing_id
    AND 1 - (le.embedding <=> ref_embedding) >= similarity_threshold
  ORDER BY le.embedding <=> ref_embedding
  LIMIT match_count;
END;
$$;
