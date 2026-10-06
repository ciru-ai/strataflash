from pathlib import Path
root = Path('release')
root.mkdir(exist_ok=True)
(root / 'manifest.json').write_text('{"version":"1.0.0"}\n', encoding='utf-8')
print('manifest prepared')
