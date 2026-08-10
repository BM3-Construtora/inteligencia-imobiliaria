-- Backfill public URLs for União Imobiliária listings.
-- DreamKeys API doesn't expose URLs but the broker site uses /imovel/{code}.
-- Code lives in raw_listings.raw_data->>'code'.

UPDATE listings l
SET url = 'https://www.imobiliariauniao.com.br/imovel/' || (rl.raw_data->>'code'),
    updated_at = NOW()
FROM raw_listings rl
WHERE l.source = 'uniao'
  AND l.url IS NULL
  AND rl.source = 'uniao'
  AND rl.source_id = l.source_id
  AND rl.raw_data->>'code' IS NOT NULL;
