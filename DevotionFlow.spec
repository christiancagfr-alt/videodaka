from pathlib import Path
import sys
import os
from PyInstaller.utils.hooks import collect_all, copy_metadata, collect_data_files

root=Path(SPECPATH)
if sys.platform=='win32':
    # Do not collect similarly named DLLs from unrelated programs on the host PATH.
    system=Path(os.environ['SystemRoot'])
    os.environ['PATH']=os.pathsep.join(str(p) for p in (
        Path(sys.base_prefix),Path(sys.base_prefix)/'DLLs',system/'System32',system))
datas=[(str(root/'app/probe.js'),'app'),(str(root/'assets/devotionflow.svg'),'assets'),(str(root/'assets/devotionflow.png'),'assets')]
binaries=[]
hiddenimports=[]
for package in ('yt_dlp','yt_dlp_ejs','keyring'):
    package_data,package_binaries,package_imports=collect_all(package)
    datas+=package_data; binaries+=package_binaries; hiddenimports+=package_imports
for package in ('gspread','openpyxl','defusedxml','PySide6','yt-dlp','keyring','google-auth-oauthlib'):
    datas+=copy_metadata(package,recursive=True)
datas+=collect_data_files('PySide6',includes=['**/LICENSE*','**/licenses/**'])

a=Analysis([str(root/'main.py')],pathex=[str(root)],binaries=binaries,datas=datas,
           hiddenimports=hiddenimports,excludes=['tkinter','pytest','pip'],noarchive=False)
pyz=PYZ(a.pure)
exe=EXE(pyz,a.scripts,[],exclude_binaries=True,name='DevotionFlow',icon=str(root/'assets/devotionflow.ico') if sys.platform=='win32' else None,console=os.environ.get('DEVOTION_BUILD_CONSOLE')=='1',
        debug=False,strip=False,upx=False,argv_emulation=False,
        codesign_identity=None,entitlements_file=None)
collection=COLLECT(exe,a.binaries,a.datas,strip=False,upx=False,name='DevotionFlow')
if sys.platform=='darwin':
    app=BUNDLE(collection,name='DevotionFlow.app',bundle_identifier='app.devotionflow.desktop',
               icon=str(root/'assets/devotionflow.icns'),
               info_plist={'CFBundleShortVersionString':'0.2.3','CFBundleVersion':'5',
                           'NSHighResolutionCapable':True})
