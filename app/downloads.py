"""Download controls use yt-dlp in an isolated, cancellable process."""
import shutil
import sys
from pathlib import Path
from urllib.parse import urlparse,parse_qs,quote
from PySide6.QtCore import QProcess
from PySide6.QtWidgets import QDialog,QVBoxLayout,QHBoxLayout,QLabel,QLineEdit,QPushButton,QTextEdit,QFileDialog
from .security import safe_error

def playlist_url(url):
    parsed=urlparse(url)
    if parsed.hostname not in ('www.youtube.com','youtube.com','m.youtube.com'): return ''
    value=parse_qs(parsed.query).get('list',[''])[0]
    return 'https://www.youtube.com/playlist?list='+quote(value,safe='') if value else ''

def download_arguments(url,directory,quality='1080',playlist=False,ffmpeg=''):
    parsed=urlparse(url)
    if len(url)>16384 or parsed.scheme not in ('https','http') or not parsed.hostname or len(parsed.hostname)>253 or parsed.username or parsed.password:
        raise ValueError('请输入有效且不含账号密码的视频网址')
    if quality not in ('720','1080','1440','2160','best'): raise ValueError('清晰度无效')
    cap='' if quality=='best' else f'[height<={quality}]'
    args=['-m','yt_dlp','--ignore-config','--no-plugin-dirs','--no-exec','--newline','--no-colors','--continue','--no-overwrites','--retries','3','--socket-timeout','20',
          '--format',f'bv*{cap}+ba/b{cap}','--merge-output-format','mkv',
          '--paths',str(directory),'--output','%(title).160B [%(id)s].%(ext)s',
          '--download-archive',str(Path(directory)/f'.downloaded-{quality}.txt'),
          '--yes-playlist' if playlist else '--no-playlist']
    if ffmpeg: args+=['--ffmpeg-location',ffmpeg]
    if shutil.which('node'): args+=['--js-runtimes','node']
    args+=['--',url]
    return args

class DownloadDialog(QDialog):
    def __init__(self,owner):
        super().__init__(owner); self.owner=owner; self.setWindowTitle('视频下载'); self.resize(760,520)
        from .ui import QComboBox
        layout=QVBoxLayout(self); layout.addWidget(QLabel('边看边下载 · 播放列表会自动读取，已下载的视频会跳过'))
        self.url=QLineEdit(); layout.addWidget(self.url)
        self.path=QLineEdit(owner.cfg['download_dir'] or str(owner.store.root/'downloads'))
        row=QHBoxLayout(); row.addWidget(QLabel('保存到')); row.addWidget(self.path,1); choose=QPushButton('选择目录'); choose.clicked.connect(self.choose); row.addWidget(choose); layout.addLayout(row)
        self.quality=QComboBox(); self.quality.addItems(['720','1080','1440','2160','best']); self.quality.setCurrentText(owner.cfg['download_quality']); layout.addWidget(QLabel('最高分辨率：1080 默认，best 为源视频最高画质')); layout.addWidget(self.quality)
        row=QHBoxLayout(); self.single=QPushButton('下载当前视频'); self.single.clicked.connect(lambda:self.start(False)); row.addWidget(self.single)
        self.playlist=QPushButton('同步当前播放列表'); self.playlist.clicked.connect(lambda:self.start(True)); row.addWidget(self.playlist)
        cancel=QPushButton('停止下载'); cancel.clicked.connect(self.stop); row.addWidget(cancel); layout.addLayout(row)
        from PySide6.QtWidgets import QPlainTextEdit
        self.output=QPlainTextEdit(); self.output.append=self.output.appendPlainText; self.output.setReadOnly(True); self.output.setMaximumBlockCount(1500); layout.addWidget(self.output)
        self.process=QProcess(self); self.process.setProcessChannelMode(QProcess.MergedChannels)
        self.process.readyReadStandardOutput.connect(self.read_output); self.process.finished.connect(self.finished)
        self.process.errorOccurred.connect(self.failed)
    def failed(self,error):
        self.output.append('下载进程错误：'+self.process.errorString()); self.single.setEnabled(True); self.playlist.setEnabled(True)
    def choose(self):
        path=QFileDialog.getExistingDirectory(self,'下载目录',self.path.text())
        if path: self.path.setText(path)
    def present(self,url):
        if self.process.state()==QProcess.NotRunning: self.url.setText(url)
        self.show(); self.raise_()
    def start(self,playlist):
        if self.process.state()!=QProcess.NotRunning: return
        import importlib.util
        if not importlib.util.find_spec('yt_dlp'): self.output.append('缺少 yt-dlp，请运行 python -m pip install -r requirements.txt'); return
        target=self.url.text().strip()
        if playlist:
            target=playlist_url(target)
            if not target: self.output.append('当前链接没有播放列表，请在 YouTube 中打开播放列表后重试。'); return
        ffmpeg=self.owner.cfg['ffmpeg_path']
        if not ffmpeg and not shutil.which('ffmpeg'):
            self.output.append('高清视频合并需要 FFmpeg。请在系统设置中选择 ffmpeg.exe 或将 FFmpeg 加入 PATH。'); return
        try:
            if not self.path.text().strip(): raise ValueError('请选择下载目录')
            directory=Path(self.path.text()).expanduser().resolve(); directory.mkdir(parents=True,exist_ok=True)
            args=download_arguments(target,directory,self.quality.currentText(),playlist,ffmpeg)
        except (OSError,ValueError) as e: self.output.append(str(e)); return
        self.owner.cfg.update(download_dir=str(directory),download_quality=self.quality.currentText()); self.owner.store.save_config(self.owner.cfg)
        for key in ('download_dir','download_quality'): self.owner.settings_page.fields[key].setText(str(self.owner.cfg[key])) if key=='download_dir' else self.owner.settings_page.fields[key].setCurrentText(self.owner.cfg[key])
        self.output.append('开始下载：'+target); self.single.setEnabled(False); self.playlist.setEnabled(False)
        if getattr(sys,'frozen',False): args=['--download-worker',*args[2:]]
        self.process.start(sys.executable,args)
    def read_output(self):
        self.output.append(safe_error(bytes(self.process.readAllStandardOutput()).decode('utf-8',errors='replace')))
    def finished(self,code,status):
        self.single.setEnabled(True); self.playlist.setEnabled(True)
        self.output.append('下载完成。' if code==0 else '下载已停止或失败，查看上方错误。再次下载可续传。')
    def stop(self):
        if self.process.state()!=QProcess.NotRunning: self.process.kill()
    def closeEvent(self,event):
        # Hide without interrupting downloads; the main window owns the process.
        event.accept()
