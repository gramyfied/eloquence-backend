-- Ajouter les colonnes manquantes
ALTER TABLE coaching_sessions ADD COLUMN IF NOT EXISTS is_multi_agent BOOLEAN DEFAULT FALSE;
ALTER TABLE session_turns ADD COLUMN IF NOT EXISTS participant_id UUID;
