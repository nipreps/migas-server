-- Quickstart SQL for local development

CREATE SCHEMA IF NOT EXISTS migas;

-- Projects Gatekeeper
CREATE TABLE IF NOT EXISTS migas.projects (
    project VARCHAR(140) PRIMARY KEY
);

INSERT INTO migas.projects (project)
VALUES ('master'), ('nipreps/nipreps')
ON CONFLICT (project) DO NOTHING;

-- Status Enum (used by crumbs)
DO $$ BEGIN
    CREATE TYPE status AS ENUM ('R', 'C', 'F', 'S');
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;

-- Users
CREATE TABLE IF NOT EXISTS migas.users (
    idx SERIAL PRIMARY KEY,
    user_id UUID UNIQUE NOT NULL,
    user_type VARCHAR(32) NOT NULL DEFAULT 'general',
    platform VARCHAR(64) DEFAULT 'unknown',
    container VARCHAR(32) NOT NULL DEFAULT 'unknown',
    geoloc_idx INTEGER
);

-- Telemetry Crumbs
CREATE TABLE IF NOT EXISTS migas.crumbs (
    idx SERIAL PRIMARY KEY,
    project VARCHAR(140) NOT NULL REFERENCES migas.projects(project),
    version VARCHAR(48) NOT NULL,
    language VARCHAR(32) NOT NULL,
    language_version VARCHAR(48) NOT NULL,
    timestamp TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    session_id UUID,
    user_id UUID REFERENCES migas.users(user_id),
    status status NOT NULL DEFAULT 'R',
    status_desc TEXT,
    error_type TEXT,
    error_desc TEXT,
    is_ci BOOLEAN NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_crumbs_project ON migas.crumbs (project);
CREATE INDEX IF NOT EXISTS ix_crumbs_project_timestamp ON migas.crumbs (project, timestamp);

-- Auth
CREATE TABLE IF NOT EXISTS migas.auth (
    idx SERIAL PRIMARY KEY,
    project VARCHAR(140) NOT NULL REFERENCES migas.projects(project),
    token VARCHAR NOT NULL UNIQUE,
    description VARCHAR,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    last_used TIMESTAMP WITH TIME ZONE
);

CREATE INDEX IF NOT EXISTS ix_migas_auth_token ON migas.auth (token);

/* Auth tokens
master: 'my_test_token'
nipreps: 'm_nipreps'
*/
INSERT INTO migas.auth (project, token, description)
VALUES
    ('master', '2f8cb05b023aef8d7f5617ff933fae44e3c40f628466d264b753661f2d08154d', 'test root'),
    ('nipreps/nipreps', '2a72f9e40024829c04222872fee37e6f3a4919a4428e78704784443eb8ae0907', 'nipreps project')
ON CONFLICT (token) DO NOTHING;
