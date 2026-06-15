#!/usr/bin/env bash
set -euo pipefail

curl -X POST "http://127.0.0.1:8000/calculate-retrofit/" \
  -H "Content-Type: application/json" \
  --data-binary "@backend/data/mock_retrofit_calculation_request.json"
