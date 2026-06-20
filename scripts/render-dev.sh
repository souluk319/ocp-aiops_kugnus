#!/usr/bin/env bash

set -euo pipefail

kubectl kustomize openshift/overlays/dev
