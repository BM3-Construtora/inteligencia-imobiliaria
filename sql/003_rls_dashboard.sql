-- Enable RLS and add read policies for the dashboard (anon key)

-- listings: public read
ALTER TABLE listings ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Allow public read on listings" ON listings
  FOR SELECT USING (true);

-- opportunities: public read
ALTER TABLE opportunities ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Allow public read on opportunities" ON opportunities
  FOR SELECT USING (true);

-- market_snapshots: public read
ALTER TABLE market_snapshots ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Allow public read on market_snapshots" ON market_snapshots
  FOR SELECT USING (true);

-- neighborhoods: public read
ALTER TABLE neighborhoods ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Allow public read on neighborhoods" ON neighborhoods
  FOR SELECT USING (true);

-- agent_runs: public read
ALTER TABLE agent_runs ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Allow public read on agent_runs" ON agent_runs
  FOR SELECT USING (true);
