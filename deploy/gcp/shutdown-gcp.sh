#!/bin/bash
SQL_INSTANCE_NAME='migas-postgres'
SERVICE_INSTANCE_NAME='migas-server'
GCP_REGION="us-central1"

SQL_EXISTS=$(gcloud sql instances list --filter name=$SQL_INSTANCE_NAME --uri)
if [[ -n $SQL_EXISTS ]]; then
    echo "Delete database"
    gcloud sql instances delete $SQL_INSTANCE_NAME --async
fi

SERVICE_EXISTS=$(gcloud run services list --filter=SERVICE:$SERVICE_INSTANCE_NAME)
if [[ -n $SERVICE_EXISTS ]]; then
    echo "Deleting service"
    gcloud run services delete $SERVICE_INSTANCE_NAME --region=$GCP_REGION --async --quiet
fi
