-- Add unique constraint on listing_id for upsert support
ALTER TABLE opportunities ADD CONSTRAINT opportunities_listing_id_key UNIQUE (listing_id);
