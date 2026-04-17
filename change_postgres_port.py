#!/bin/bash
# Change PostgreSQL port from 5432 to 5433

echo "Changing PostgreSQL port to 5433..."

# Find PostgreSQL configuration file
PG_CONF=$(sudo -u postgres psql -t -c "SHOW config_file;" | tr -d ' ')

if [ -z "$PG_CONF" ]; then
    echo "Could not find PostgreSQL config file, using default path"
    PG_CONF="/etc/postgresql/16/main/postgresql.conf"
fi

echo "PostgreSQL config file: $PG_CONF"

# Backup current config
sudo cp "$PG_CONF" "$PG_CONF.backup"

# Change port from 5432 to 5433
sudo sed -i 's/^port = 5432/port = 5433/' "$PG_CONF"
sudo sed -i 's/^#port = 5432/port = 5433/' "$PG_CONF"

# If no port directive found, add one
if ! grep -q "^port = 5433" "$PG_CONF"; then
    echo "port = 5433" | sudo tee -a "$PG_CONF"
fi

echo "PostgreSQL configuration updated to port 5433"

# Restart PostgreSQL
echo "Restarting PostgreSQL service..."
sudo systemctl restart postgresql

# Wait for service to start
sleep 5

# Check if PostgreSQL is listening on new port
echo "Checking if PostgreSQL is listening on port 5433:"
ss -tlnp | grep :5433

echo "Port change completed!"
