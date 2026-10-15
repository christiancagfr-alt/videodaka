import argparse
import sys
import json
from pathlib import Path
from PySide6.QtCore import QLockFile,QTimer,QEventLoop
from PySide6.QtWidgets import QApplication,QMessageBox
from app.ui import Window

def main():
    if len(sys.argv)>1 and sys.argv[1]=='--download-worker':
        # Windowed executables have no Python streams, even when QProcess supplies pipes.
        import os
        for name,fd in (('stdout',1),('stderr',2)):
            if getattr(sys,name) is None:
                try: stream=open(fd,'w',encoding='utf-8',errors='replace',closefd=False)
                except OSError: stream=open(os.devnull,'w',encoding='utf-8')
                setattr(sys,name,stream)
        import yt_dlp
        yt_dlp.main(sys.argv[2:]); return 0
    from PySide6.QtCore import QStandardPaths
    QApplication.setOrganizationName('DevotionFlow'); QApplication.setApplicationName('DevotionFlow')
    default_data=Path(QStandardPaths.writableLocation(QStandardPaths.AppLocalDataLocation)) if getattr(sys,'frozen',False) else Path(__file__).parent/'data'
    parser=argparse.ArgumentParser(); parser.add_argument('--demo',action='store_true'); parser.add_argument('--smoke',action='store_true'); parser.add_argument('--smoke-live',action='store_true'); parser.add_argument('--data-dir',type=Path,default=default_data); args=parser.parse_args()
    args.data_dir.mkdir(parents=True,exist_ok=True)
    app=QApplication(sys.argv); lock=QLockFile(str(args.data_dir/'app.lock')); lock.setStaleLockTime(0)
    if not lock.tryLock(0): QMessageBox.information(None,'静心','程序已在运行。'); return 1
    window=Window(args.data_dir,args.demo or args.smoke); window.show()
    if args.smoke or args.smoke_live:
        def finish():
            window.grab().save(str(args.data_dir/'smoke.png'))
            for i in range(4):
                window.select_page(i); app.processEvents(); window.grab().save(str(args.data_dir/f'page-{i}.png'))
            window.enter_fullscreen(); app.processEvents()
            assert window.fullscreen_active and window.quicklog.isHidden() and window.sidebar.isHidden()
            render_wait=QEventLoop(); QTimer.singleShot(700,render_wait.quit); render_wait.exec()
            window.grab().save(str(args.data_dir/'fullscreen.png'))
            window.exit_fullscreen(); app.processEvents()
            assert not window.fullscreen_active and not window.quicklog.isHidden()
            window.select_page(0)
            def checked(result):
                (args.data_dir/'browser-check.json').write_text(json.dumps({'url':window.browser.url().toString(),'document':result},ensure_ascii=False),'utf-8')
                from app.ui import Settings
                dialog=Settings(window.cfg,window); dialog.show(); app.processEvents(); dialog.grab().save(str(args.data_dir/'settings.png')); dialog.close()
                window.close(); app.quit()
            window.browser.page().runJavaScript('document.body.innerText',checked)
        QTimer.singleShot(25000 if args.smoke_live else 10000,finish)
    return app.exec()

if __name__=='__main__': sys.exit(main())
