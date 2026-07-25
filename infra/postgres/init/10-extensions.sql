-- Runs only when PostgreSQL initialises an empty data directory.
--
-- Creating the extension here means the application's database role never needs
-- superuser rights in environments where migrations run as a restricted user.
-- The Alembic baseline also issues CREATE EXTENSION IF NOT EXISTS, so either path
-- produces the same schema.
CREATE EXTENSION IF NOT EXISTS vector;
