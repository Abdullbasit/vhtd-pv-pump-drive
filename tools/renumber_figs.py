"""Renumber the manuscript's figures by order of first citation in the body; re-sort the Figures list."""
import re, sys
f = sys.argv[1]; s = open(f, encoding='utf-8').read()
i_figs = s.index('\n## Figures'); body = s[:i_figs]; rest = s[i_figs:]
tok = re.compile(r'Figs?\. (\d+(?:[–\-]\d+)?(?:, \d+(?:[–\-]\d+)?)*)')
def expand(lst):
    out = []
    for part in lst.split(', '):
        r = re.split(r'[–\-]', part); a = int(r[0]); b = int(r[1]) if len(r) > 1 else a; out.extend(range(a, b + 1))
    return out
order = []
for m in tok.finditer(body):
    for n in expand(m.group(1)):
        if n not in order: order.append(n)
for n in [int(x) for x in re.findall(r'^- Fig\. (\d+) —', rest, re.M)]:
    if n not in order: order.append(n)
new = {old: i + 1 for i, old in enumerate(order)}
def collapse(nums):
    nums = sorted(set(nums)); runs = []; a = b = nums[0]
    for n in nums[1:]:
        if n == b + 1: b = n
        else: runs.append((a, b)); a = b = n
    runs.append((a, b))
    return ', '.join(('%d' % a) if a == b else ('%d–%d' % (a, b)) if b > a + 1 else ('%d, %d' % (a, b)) for a, b in runs)
def sub(m):
    nums = [new[n] for n in expand(m.group(1))]
    return ('Fig.' if len(nums) == 1 else 'Figs.') + ' ' + collapse(nums)
s2 = tok.sub(sub, s)
lines = s2.split('\n'); start = next(i for i, l in enumerate(lines) if l.startswith('## Figures')); j = start + 1
while j < len(lines) and not lines[j].startswith('## '): j += 1
block = lines[start + 1:j]; items = [l for l in block if l.startswith('- Fig. ')]; others = [l for l in block if not l.startswith('- Fig. ') and l.strip()]
items.sort(key=lambda l: (int(re.match(r'- Fig\. (\d+)', l).group(1)), '(continued)' in l))
lines[start + 1:j] = [''] + items + [''] + others + ['']
open(f, 'w', encoding='utf-8').write('\n'.join(lines))
print('map', {k: v for k, v in new.items() if k != v} or 'identity')
