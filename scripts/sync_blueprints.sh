#!/usr/bin/env sh
# Copy the source-of-truth blueprints into the integration so they ship with it.
set -e
cd "$(dirname "$0")/.."
mkdir -p custom_components/appliance_live_activity/blueprints
cp blueprints/automation/*.yaml custom_components/appliance_live_activity/blueprints/
echo "Blueprints synced."
