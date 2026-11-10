import os, re

replacements = {
    r'font-family:monospace': 'font-family: var(--font-mono)',
    r"font-family:'Consolas','Courier New',monospace": 'font-family: var(--font-mono)',
    r'font-family:"Consolas","Courier New",monospace': 'font-family: var(--font-mono)',
    r'font-family:inherit': 'font-family: var(--font-ui)',
}

for root, dirs, files in os.walk('D:/Data/Files/ptos/web_templates'):
    for f in files:
        if f.endswith('.html'):
            path = os.path.join(root, f)
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                original = content
                for old, new in replacements.items():
                    content = re.sub(old, new, content)
                
                if content != original:
                    with open(path, 'w', encoding='utf-8') as f:
                        f.write(content)
                    print(f'Updated {path}')
            except Exception as e:
                print(f'Error processing {path}: {e}')