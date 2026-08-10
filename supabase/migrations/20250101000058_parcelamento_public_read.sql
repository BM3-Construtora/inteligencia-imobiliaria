-- 20250101000058_parcelamento_public_read.sql
-- Libera leitura anônima de parcelamento_solo_marilia para o dashboard.
--
-- Contexto: a tabela habilita RLS (migration 043) sem policy de SELECT, então
-- fica deny-by-default para a anon key — a tela "Novos Loteamentos" do
-- dashboard vinha vazia. São loteamentos/desmembramentos aprovados publicados
-- no Diário Oficial (dado público, não é o edge competitivo da BM3), coerente
-- com radar_concorrencia (alvarás/EIV) já ser público. O backend usa
-- service_role e ignora RLS.
--
-- NÃO reabrimos avm_predictions nem construtoras_rating: a migration
-- rls_hardening (056) os fechou de propósito por serem sinais de negociação
-- sensíveis. A tela "Subprecificados" do dashboard depende de avm_predictions
-- e permanece bloqueada por essa decisão — ver nota de arquitetura ao final.

DROP POLICY IF EXISTS "Allow public read on parcelamento_solo_marilia" ON parcelamento_solo_marilia;
CREATE POLICY "Allow public read on parcelamento_solo_marilia"
    ON parcelamento_solo_marilia FOR SELECT TO anon
    USING (true);

-- Nota de arquitetura (ADR pendente): expor os preços justos do AVM
-- (avm_predictions) ao browser conflita com o hardening. Para a tela
-- "Subprecificados" funcionar sem reabrir o dado sensível, o caminho é
-- (a) Supabase Auth no dashboard, ou (b) uma RPC SECURITY DEFINER que exponha
-- apenas o recorte necessário. Decisão do dono do produto.
