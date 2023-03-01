export MIGAS_REDIS_URI='redis://localhost'
export DATABASE_URL='postgres://localhost/migas'
export MIGAS_DEBUG=1
export MIGAS_MAX_REQUESTS_PER_WINDOW=50
export MIGAS_MAX_REQUEST_SIZE=3000

migas-server --reload
