CREATE SCHEMA IF NOT EXISTS migas;

CREATE TABLE IF NOT EXISTS migas.auth (
    idx SERIAL PRIMARY KEY,
    project VARCHAR(140) NOT NULL,
    token VARCHAR NOT NULL UNIQUE,
    description VARCHAR,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    last_used TIMESTAMP WITH TIME ZONE
);

CREATE INDEX IF NOT EXISTS ix_migas_auth_token ON migas.auth (token);

INSERT INTO migas.auth (project, token, description)
VALUES ('master', '2f8cb05b023aef8d7f5617ff933fae44e3c40f628466d264b753661f2d08154d', 'test root')
ON CONFLICT (token) DO NOTHING;
