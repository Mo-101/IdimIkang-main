-- Idim Ikang v1.5-quant-alpha Migration
-- Add columns for Scale-out/Breakeven management
ALTER TABLE signals ADD COLUMN IF NOT EXISTS is_partial BOOLEAN DEFAULT FALSE;
ALTER TABLE signals ADD COLUMN IF NOT EXISTS trailing_sl NUMERIC;

-- Update outcome check constraint for institutional outcomes
-- Note: Requires dropping existing constraint first
ALTER TABLE signals DROP CONSTRAINT IF EXISTS signals_outcome_check;
ALTER TABLE signals ADD CONSTRAINT signals_outcome_check CHECK (outcome IN ('WIN', 'LOSS', 'EXPIRED', 'PARTIAL_WIN', 'ARCHIVED_V1'));
