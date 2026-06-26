#!/usr/bin/env bash

set -euo pipefail

FILE_PATTERNS=(
  "src/**/*.{js,jsx,ts,tsx,json}"
  "integration-tests/**/*.{js,jsx,ts,tsx,json}"
  "i18n-scripts/**/*.{js,json}"
  "*.{js,jsx,ts,tsx,json}"
)

mkdir -p "dist/locales/en"
i18next "${FILE_PATTERNS[@]}" -c "./i18next-parser.config.js" -o "locales/\$LOCALE/\$NAMESPACE.json"
