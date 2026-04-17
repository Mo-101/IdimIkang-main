#!/bin/bash
# Check PostgreSQL port and configuration

echo "Current PostgreSQL configuration:"

# Check current port
sudo -u postgres psql -c "SHOW port;" 2>/dev/null || echo "Failed to get port"

# Check listen addresses  
sudo -u postgres psql -c "SHOW listen_addresses;" 2>/dev/null || echo "Failed to get listen addresses"

# Check if PostgreSQL is running on port 5432
echo "Checking if PostgreSQL is listening on port 5432:"
netstat -tlnp | grep :5432 || echo "Port 5432 not found in netstat"

# Check PostgreSQL service status
echo "PostgreSQL service status:"
sudo systemctl status postgresql | head -10
