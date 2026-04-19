#!/bin/bash
echo "🚀 Deployando Paula Pilates..."

docker build -t gcr.io/paula-pilates-app/paula-pilates .
docker push gcr.io/paula-pilates-app/paula-pilates
gcloud run deploy paula-pilates \
  --image gcr.io/paula-pilates-app/paula-pilates \
  --region southamerica-west1 \
  --allow-unauthenticated

echo "✅ Deploy completado!"
