#!/bin/sh

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<EOSQL
    CREATE SCHEMA IF NOT EXISTS migas;
    SET search_path to migas;
    CREATE TABLE IF NOT EXISTS projects (project VARCHAR(140) PRIMARY KEY);
    INSERT INTO projects (project) VALUES ('nipreps/migas-server');
    CREATE TYPE STATUS as ENUM ('R', 'C', 'F', 'S');
    CREATE TABLE IF NOT EXISTS "nipreps/migas-server" (
        idx BIGSERIAL PRIMARY KEY,
        version VARCHAR(24) NOT NULL,
        language VARCHAR(32) NOT NULL,
        language_version VARCHAR(24) NOT NULL,
        timestamp TIMESTAMPTZ NOT NULL,
        session_ID UUID,
        user_id UUID,
        status STATUS NOT NULL,
        status_desc VARCHAR,
        error_type VARCHAR,
        error_desc VARCHAR,
        is_ci BOOLEAN NOT NULL);
EOSQL

# SET TIMEZONE="Americas/New_York";
# SELECT t.day::timestamptz FROM  (
#     generate_series(timestamp '2020-01-01',
#                     timestamp '2022-07-19',
#                     interval  '1 day') AS t(day);

