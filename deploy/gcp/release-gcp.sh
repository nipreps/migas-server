#!/bin/bash

# This script uses the `gcloud` SDK to:
# - Check for required resources
# - Create required resources if necessary (optional)
# - Deploy the application

set -eux

# Set default ENVVARS
PROJECT="migas"
PROJECT_ID="migas-362318"
GCP_REGION="us-central1"
SQL_INSTANCE_NAME="migas-postgres"
SQL_INSTANCE_PASSWORD="foobar"
GCP_SERVICE_NAME="migas-server"

HERE=$(dirname $(realpath $0))
ROOT=$(dirname $(dirname $HERE))

# Step 0: Install SDK
# https://github.com/google-github-actions/setup-gcloud

# Step 1: Check for SQL database
SQL_EXISTS=$(gcloud sql instances list --filter name=$SQL_INSTANCE_NAME --uri)

if [[ -z $SQL_EXISTS ]]; then
    # Step 1.5: If not, create it
    gcloud sql instances create $SQL_INSTANCE_NAME \
        --database-version=POSTGRES_14 \
        --cpu=2 \
        --memory=8GiB \
        --region=$GCP_REGION \
        --root-password=$SQL_INSTANCE_PASSWORD \
        --insights-config-query-insights-enabled

    # create migas database
    gcloud sql databases create migas --instance=migas-postgres
fi

# # Build the service distribution
# if [ -d $ROOT/dist ]; then
#     echo "Remove previous build"
#     rm -rf $ROOT/dist
# fi
# python -m build -o $ROOT/dist
# src=$(ls $ROOT/dist/*tar.gz)

# Step 2: Build the service image
GCR_TAG=gcr.io/$PROJECT_ID/$GCP_SERVICE_NAME
gcloud builds submit \
    --tag $GCR_TAG

# Step 3: Deploy the service
gcloud run deploy $GCP_SERVICE_NAME \
    --region=$GCP_REGION \
    --image=$GCR_TAG \
    --platform=managed \
    --min-instances=1 \
    --max-instances=3 \
    --ingress=all \
    --allow-unauthenticated \
    --set-cloudsql-instances="$PROJECT_ID:$GCP_REGION:$SQL_INSTANCE_NAME" \
    --memory=512Mi \
    --cpu=2 \
    --args=--port,8080,--proxy-headers,--headers,X-Backend-Server:migas \
    --env-vars-file="$HERE/.env"

# # Step ??: Map service to custom domain
# gcloud domains verify nipreps.org
# gcloud beta run domain-mappings create --service $SERVICE_NAME --domain migas.nipreps.org
# # Generate DNS record
# gcloud beta run domain-mappings describe --domain migas.nipreps.org
