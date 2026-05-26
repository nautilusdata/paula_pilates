#!/bin/bash
cd "$(dirname "$0")/academia"   # siempre desde academia/
echo "🚀 Deployando Paula Pilates en modo Cloud-Native..."
gcloud run deploy paula-pilates \
  --source . \
  --region southamerica-west1 \
  --allow-unauthenticated
echo "✅ Deploy completado en la nube!"