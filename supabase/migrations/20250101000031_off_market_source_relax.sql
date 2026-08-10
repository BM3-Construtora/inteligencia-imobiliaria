-- Relaxa CHECK source em off_market_signals para aceitar fontes adicionais
-- (leilao_generico via LEILOES_FEED_URL configurável).

ALTER TABLE off_market_signals DROP CONSTRAINT IF EXISTS off_market_signals_source_check;

ALTER TABLE off_market_signals
  ADD CONSTRAINT off_market_signals_source_check
  CHECK (source IN (
    'leilao_caixa',
    'leilao_generico',
    'leilao_judicial',
    'iptu_devedor',
    'alvara_prefeitura',
    'inventario_tjsp'
  ));
