from pathlib import Path
import sys
from PyInstaller.utils.hooks import collect_all, copy_metadata, collect_data_files

root=Path(SPECPATH)
datas=[(str(root/'app/probe.js'),'app')]
binaries=[]
hiddenimports=[]
for package in ('yt_dlp','yt_dlp_ejs'):
    package_data,package_binaries,package_imports=collect_all(package)
    datas+=package_data; binaries+=package_binaries; hiddenimports+=package_imports
for package in ('gspread','openpyxl','defusedxml','PySide6','yt-dlp'):
    datas+=copy_metadata(package,recursive=True)
datas+=collect_data_files('PySide6',includes=['**/LICENSE*','**/licenses/**'])

a=Analysis([str(root/'main.py')],pathex=[str(root)],binaries=binaries,datas=datas,
           hiddenimports=hiddenimports,excludes=['tkinter','pytest','pip'],noarchive=False)
pyz=PYZ(a.pure)
exe=EXE(pyz,a.scripts,[],exclude_binaries=True,name='DevotionFlow',console=False,
        debug=False,strip=False,upx=False,argv_emulation=False,
        codesign_identity=None,entitlements_file=None)
collection=COLLECT(exe,a.binaries,a.datas,strip=False,upx=False,name='DevotionFlow')
if sys.platform=='darwin':
    app=BUNDLE(collection,name='DevotionFlow.app',bundle_identifier='app.devotionflow.desktop',
               info_plist={'CFBundleShortVersionString':'0.1.0','CFBundleVersion':'1',
                           'NSHighResolutionCapable':True})
