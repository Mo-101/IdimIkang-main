import sys

file_path = '/home/idona/MoStar/IdimIkang-main-1/observer_bundle/scanner.py'
with open(file_path, 'r') as f:
    lines = f.readlines()

start_marker = '            # ── v1.5 Filter Patch: pre-emission gates ──────────────'
end_marker = '            # ── end v1.5 Filter Patch ──────────────────────────────'

new_logic = """            # ── Idim Gate Patch v1 (Post-Execution Selection) ──────
            emitted = []
            for s in selected:
                # Normalizing for apply_gates expectation
                _s_dict = {
                    'pair': s['pair'],
                    'side': s['side'],
                    'score': float(s['score']),
                    'regime': s.get('regime', ''),
                    'btc_regime': s.get('btc_regime', 'UNKNOWN'),
                    'family': s.get('signal_family', 'none').upper()
                }
                
                ok, reason = apply_gates(_s_dict)
                if not ok:
                    logger.info(
                        '[GATE_BLOCKED] reason=%s pair=%s side=%s score=%.2f regime=%s family=%s',
                        reason, s['pair'], s['side'], s['score'], 
                        s.get('regime', ''), s.get('signal_family', 'none')
                    )
                    continue
                
                emitted.append(s)
"""

start_idx = -1
end_idx = -1

for i, line in enumerate(lines):
    if start_marker in line:
        start_idx = i
    if end_marker in line:
        end_idx = i
        break

if start_idx != -1 and end_idx != -1:
    print(f'Patching from line {start_idx} to {end_idx}')
    lines[start_idx:end_idx] = [new_logic]
    with open(file_path, 'w') as f:
        f.writelines(lines)
    print('Successfully patched scanner.py')
else:
    print(f'Markers not found: start={start_idx}, end={end_idx}')
    sys.exit(1)
