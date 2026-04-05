#!/bin/bash

# MoStar Sovereign v1.5 [Institutional Log Monitor]
# Streams colorized logs for the entire Idim Ikang stack.

# Color definitions
RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

echo -e "${CYAN}--- [ SOVEREIGN v1.5 WATCHER ] ---${NC}"
echo -e "${YELLOW}Streaming logs for: idim-scanner, idim-api, idim-dashboard${NC}"
echo -e "${YELLOW}Press CTRL+C to terminate the stream.${NC}\n"

# Use pm2 to stream all relevant logs
# We use --lines 50 to get context immediately
pm2 logs idim-scanner idim-api idim-dashboard --lines 50
