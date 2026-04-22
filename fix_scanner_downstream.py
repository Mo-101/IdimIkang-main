import sys

file_path = '/home/idona/MoStar/IdimIkang-main-1/observer_bundle/scanner.py'
with open(file_path, 'r') as f:
    lines = f.readlines()

# 1. Defensive fix for family
old_line_1 = "                'family': s.get('signal_family', 'none').upper()"
new_line_1 = "                'family': (s.get('signal_family') or 'none').upper()"

# 2. Fix telemetry and alerts usage of len(selected) -> len(emitted)
old_line_2 = '                "signals_emitted": len(selected),'
new_line_2 = '                "signals_emitted": len(emitted),'

old_line_3 = '                f"Scan cycle completed: {pairs_processed} pairs / {len(selected)} signals emitted",'
new_line_3 = '                f"Scan cycle completed: {pairs_processed} pairs / {len(emitted)} signals emitted",'

patched_count = 0
for i, line in enumerate(lines):
    if old_line_1 in line:
        lines[i] = line.replace(old_line_1, new_line_1)
        patched_count += 1
    if old_line_2 in line:
        lines[i] = line.replace(old_line_2, new_line_2)
        patched_count += 1
    if old_line_3 in line:
        lines[i] = line.replace(old_line_3, new_line_3)
        patched_count += 1

if patched_count > 0:
    print(f'Successfully applied {patched_count} downstream fixes to scanner.py')
    with open(file_path, 'w') as f:
        f.writelines(lines)
else:
    print('No markers found to patch.')
    sys.exit(1)
