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

-- Projects
CREATE TABLE IF NOT EXISTS migas.projects (
    project VARCHAR(140) PRIMARY KEY
);

INSERT INTO migas.projects (project)
VALUES ('nipreps/nipreps')
ON CONFLICT (project) DO NOTHING;

/* Auth tokens
master: 'my_test_token'
nipreps: 'm_nipreps'
*/
INSERT INTO migas.auth (project, token, description)
VALUES
    ('master', '2f8cb05b023aef8d7f5617ff933fae44e3c40f628466d264b753661f2d08154d', 'test root'),
    ('nipreps/nipreps', '2a72f9e40024829c04222872fee37e6f3a4919a4428e78704784443eb8ae0907', 'nipreps project')
ON CONFLICT (token) DO NOTHING;
