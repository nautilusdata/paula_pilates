#!/bin/bash
echo "🚀 Deployando Paula Pilates en modo Cloud-Native..."

# Usamos --source . para que Cloud Build haga el docker build y push por atrás
gcloud run deploy paula-pilates \
  --source . \
  --region southamerica-west1 \
  --allow-unauthenticated

echo "✅ Deploy completado en la nube!"
