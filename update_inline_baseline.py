import json
import pathlib
import re

CSS_DIR = pathlib.Path('web_static/css')
BASELINE_FILE = pathlib.Path('tests/inline_style_baseline.json')

def strip_comments(css):
    return re.sub(r'/\*.*?\*/', '', css, flags=re.S)

def count_file(path):
    raw = path.read_text(encoding='utf-8')
    return raw.count('style="')

counts = {}
for f in sorted(pathlib.Path('web_templates').rglob('*.html')):
    rel = f.relative_to('web_templates').as_posix()
    text = f.read_text(encoding='utf-8')
    counts[rel] = text.count('style="')

for f in sorted(pathlib.Path('web_static/js').rglob('*.js')):
    rel = f.relative_to('web_static/js').as_posix()
    text = f.read_text(encoding='utf-8')
    counts[rel] = text.count('style="')

with open('tests/inline_style_baseline.json', 'w') as f:
    json.dump(counts, f, indent=2, sort_keys=True)
    f.write('\n')
print('Baseline updated:', counts)