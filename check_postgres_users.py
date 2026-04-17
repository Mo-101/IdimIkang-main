#!/bin/bash
# Check PostgreSQL users and reset password if needed

echo "Checking PostgreSQL users..."

# First, let's try to connect as postgres without password to see current users
sudo -u postgres psql -c "SELECT usename FROM pg_user;" 2>/dev/null || {
    echo "Failed to connect as postgres user"
    exit 1
}

echo "Attempting to reset postgres password..."
sudo -u postgres psql -c "ALTER USER postgres PASSWORD 'IdimIkangLocal2026!';"

echo "Testing connection with new password..."
PGPASSWORD="IdimIkangLocal2026!" psql -h localhost -U postgres -d idim_ikang -c "SELECT 'Connection successful' as status;" 2>/dev/null && {
    echo "Database connection restored successfully!"
} || {
    echo "Still having connection issues. Checking PostgreSQL status..."
    sudo systemctl status postgresql
}
