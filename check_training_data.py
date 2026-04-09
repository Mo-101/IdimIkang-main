import psycopg2

conn = psycopg2.connect("postgresql://postgres:IdimIkangLocal2026!@localhost:5432/idim_ikang")
cur = conn.cursor()

# Check training records count
cur.execute("SELECT COUNT(*) FROM training_candidates")
total_records = cur.fetchone()[0] # type: ignore

# Check records with new fields
cur.execute("SELECT COUNT(*) FROM training_candidates WHERE family_indicators IS NOT NULL")
records_with_family_indicators = cur.fetchone()[0] # pyright: ignore[reportOptionalSubscript]

cur.execute("SELECT COUNT(*) FROM training_candidates WHERE trace_data IS NOT NULL")
records_with_trace_data = cur.fetchone()[0]  # type: ignore

# Check rejection gate distribution
cur.execute("""
    SELECT rejection_gate, COUNT(*) 
    FROM training_candidates 
    GROUP BY rejection_gate 
    ORDER BY COUNT(*) DESC
""")
gate_distribution = cur.fetchall()

# Check side distribution
cur.execute("SELECT side, COUNT(*) FROM training_candidates GROUP BY side")
side_distribution = cur.fetchall()

print(f"Total training records: {total_records}")
print(f"Records with family_indicators: {records_with_family_indicators}")
print(f"Records with trace_data: {records_with_trace_data}")
print("\nRejection gate distribution:")
for gate, count in gate_distribution:
    print(f"  {gate}: {count}")
print("\nSide distribution:")
for side, count in side_distribution:
    print(f"  {side}: {count}")

conn.close()
