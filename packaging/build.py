"""Build native installers on each platform. Never package the workspace as a whole."""
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tempfile

root=Path(__file__).resolve().parents[1]
os.chdir(root)
subprocess.run([sys.executable,'packaging/icons.py'],check=True)
if sys.platform=='darwin':
    import shutil
    iconset=root/'build/DevotionFlow.iconset'; iconset.mkdir(parents=True,exist_ok=True)
    from PySide6.QtCore import Qt,QSize
    from PySide6.QtGui import QImage,QPainter
    from PySide6.QtSvg import QSvgRenderer
    renderer=QSvgRenderer(str(root/'assets/devotionflow.svg'))
    for size in (16,32,128,256,512):
        for factor in (1,2):
            pixels=size*factor; image=QImage(QSize(pixels,pixels),QImage.Format.Format_ARGB32_Premultiplied); image.fill(Qt.transparent)
            painter=QPainter(image); renderer.render(painter); painter.end()
            suffix='@2x' if factor==2 else ''
            image.save(str(iconset/f'icon_{size}x{size}{suffix}.png'))
    subprocess.run(['iconutil','-c','icns',str(iconset),'-o',str(root/'assets/devotionflow.icns')],check=True)
subprocess.run([sys.executable,'-m','PyInstaller','--noconfirm','DevotionFlow.spec'],check=True)
release=root/'release'; release.mkdir(exist_ok=True)
executable=root/'dist'/('DevotionFlow/DevotionFlow.exe' if sys.platform=='win32' else 'DevotionFlow.app/Contents/MacOS/DevotionFlow')
with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
    smoke_env=os.environ.copy()
    smoke_env.setdefault('QTWEBENGINE_CHROMIUM_FLAGS','--disable-gpu --disable-gpu-compositing --disable-features=VizDisplayCompositor --use-gl=angle --use-angle=swiftshader --no-sandbox')
    subprocess.run([str(executable),'--smoke','--data-dir',temp],check=True,timeout=120,env=smoke_env)
    evidence=json.loads((Path(temp)/'browser-check.json').read_text('utf-8'))
    if '本地演示' not in str(evidence['document']): raise RuntimeError('Packaged WebEngine did not render the demo')
    worker=subprocess.run([str(executable),'--download-worker','--ignore-config','--no-plugin-dirs','--version'],
                          capture_output=True,text=True,timeout=60)
    if worker.returncode: raise RuntimeError('Packaged downloader failed: '+worker.stderr)
    print('Packaged browser/fullscreen/downloader smoke checks passed')

# Check both distribution layouts; aliases/symlinks are legitimate in macOS bundles.
for path in (root/'dist').rglob('*'):
    if path.is_file() and (path.name.lower() in {'settings.json','records.sqlite','security-audit.txt'}
                          or path.suffix.lower() in {'.xlsx','.pfx','.p12'}):
        raise RuntimeError('Unexpected private file in package: '+str(path))
if sys.platform=='win32':
    compiler=shutil.which('ISCC.exe')
    if not compiler:
        candidate=Path(os.environ.get('ProgramFiles(x86)',r'C:\Program Files (x86)'))/'Inno Setup 6/ISCC.exe'
        if candidate.exists(): compiler=str(candidate)
    if not compiler: raise RuntimeError('Inno Setup 6 is required to create the Windows installer')
    subprocess.run([compiler,str(root/'packaging/windows.iss')],check=True)
else:
    staging=root/'build/dmg'; staging.mkdir(parents=True,exist_ok=True)
    subprocess.run(['ditto',str(root/'dist/DevotionFlow.app'),str(staging/'DevotionFlow.app')],check=True)
    link=staging/'Applications'
    if not link.exists(): link.symlink_to('/Applications')
    target=release/f'DevotionFlow-0.2.1-macos-{platform.machine()}.dmg'
    subprocess.run(['hdiutil','create','-ov','-volname','DevotionFlow','-srcfolder',str(staging),
                    '-format','UDZO',str(target)],check=True)
checksums=[]
for path in sorted(release.iterdir()):
    if path.suffix in {'.exe','.dmg'}:
        digest=hashlib.file_digest(path.open('rb'),'sha256').hexdigest()
        checksums.append(f'{digest}  {path.name}')
(release/f'SHA256SUMS-{platform.system()}-{platform.machine()}.txt').write_text('\n'.join(checksums)+'\n','utf-8')
