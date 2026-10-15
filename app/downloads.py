"""Download controls use yt-dlp in an isolated, cancellable process."""
import shutil
import sys
import os
from pathlib import Path
from urllib.parse import urlparse,parse_qs,quote
from PySide6.QtCore import QProcess
from PySide6.QtWidgets import QDialog,QVBoxLayout,QHBoxLayout,QLabel,QLineEdit,QPushButton,QTextEdit,QFileDialog,QComboBox,QCheckBox,QDialogButtonBox,QMessageBox
from .security import safe_error

def find_ffmpeg(configured='',which=None):
    """Return a usable FFmpeg file path from settings, PATH or common install links."""
    lookup=which or shutil.which
    candidates=[]
    if configured: candidates.append(Path(configured).expanduser())
    for name in ('ffmpeg.exe','ffmpeg'):
        found=lookup(name)
        if found: candidates.append(Path(found).expanduser())
    if sys.platform=='win32':
        links=Path(os.environ.get('LOCALAPPDATA',''))/'Microsoft'/'WinGet'/'Links'
        candidates.extend((links/'ffmpeg.exe',links/'ffmpeg'))
    elif sys.platform=='darwin':
        candidates.extend((Path('/opt/homebrew/bin/ffmpeg'),Path('/usr/local/bin/ffmpeg')))
    for candidate in candidates:
        try:
            if candidate.is_file(): return str(candidate.resolve())
        except (OSError,RuntimeError): pass
    return ''

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
        self.install_process=QProcess(self); self.install_process.setProcessChannelMode(QProcess.MergedChannels)
        self.install_process.readyReadStandardOutput.connect(lambda:self.output.append(safe_error(bytes(self.install_process.readAllStandardOutput()).decode('utf-8',errors='replace'))))
        self.install_process.finished.connect(self.ffmpeg_installed); self.install_process.errorOccurred.connect(lambda _error:self.output.append('FFmpeg 安装进程启动失败：'+self.install_process.errorString())); self.queue=[]; self.seen=set(); self.settings_dialog=None; self.ffmpeg_field=None; self.ffmpeg_status=None; self.ffmpeg_install_button=None
    def open_settings(self):
        if self.settings_dialog:
            self.settings_dialog.show(); self.settings_dialog.raise_(); return
        dialog=QDialog(self.owner); dialog.setWindowTitle('下载与播放设置'); dialog.resize(600,430); form=QVBoxLayout(dialog)
        self.auto_box=QCheckBox('边看边下载：播放视频时自动排队下载'); self.auto_box.setChecked(bool(self.owner.cfg.get('watch_download'))); form.addWidget(self.auto_box)
        form.addWidget(QLabel('手动下载始终可在播放页点击“下载当前视频”；自动模式仅在浏览器播放真实 YouTube 视频时运行。'))
        self.auto_install_box=QCheckBox('缺少 FFmpeg 时使用系统包管理器自动安装'); self.auto_install_box.setChecked(bool(self.owner.cfg.get('auto_install_ffmpeg',True))); form.addWidget(self.auto_install_box)
        quality=QComboBox(); quality.addItems(['720','1080','1440','2160','best']); quality.setCurrentText(self.owner.cfg['download_quality']); form.addWidget(QLabel('最高分辨率（默认 1080p）')); form.addWidget(quality)
        path_row=QHBoxLayout(); directory=QLineEdit(self.owner.cfg.get('download_dir') or str(self.owner.store.root/'downloads')); pick=QPushButton('选择目录…')
        pick.clicked.connect(lambda:self._pick_directory(directory)); path_row.addWidget(QLabel('下载目录')); path_row.addWidget(directory,1); path_row.addWidget(pick); form.addLayout(path_row)
        ffmpeg_row=QHBoxLayout(); ffmpeg=QLineEdit(self.owner.cfg.get('ffmpeg_path','')); ffmpeg.setPlaceholderText('留空自动检测 PATH 或自动安装'); ffmpeg_pick=QPushButton('选择 FFmpeg…')
        ffmpeg_pick.clicked.connect(lambda:self._pick_ffmpeg(ffmpeg)); ffmpeg_row.addWidget(QLabel('手动指定')); ffmpeg_row.addWidget(ffmpeg,1); ffmpeg_row.addWidget(ffmpeg_pick); form.addLayout(ffmpeg_row)
        ffmpeg_actions=QHBoxLayout(); detect=QPushButton('检测并保存路径'); install=QPushButton('安装 FFmpeg'); self.ffmpeg_status=QLabel(); self.ffmpeg_status.setWordWrap(True)
        detect.clicked.connect(lambda:self.detect_ffmpeg(ffmpeg,self.ffmpeg_status)); install.clicked.connect(lambda:self.install_ffmpeg('',resume_download=False))
        ffmpeg_actions.addWidget(detect); ffmpeg_actions.addWidget(install); form.addLayout(ffmpeg_actions); form.addWidget(self.ffmpeg_status)
        self.ffmpeg_field=ffmpeg; self.ffmpeg_install_button=install
        self.detect_ffmpeg(ffmpeg,self.ffmpeg_status)
        save=QDialogButtonBox(QDialogButtonBox.Save|QDialogButtonBox.Cancel); save.accepted.connect(lambda:self._save_settings(dialog,directory,quality,ffmpeg)); save.rejected.connect(dialog.reject); form.addWidget(save)
        self.settings_dialog=dialog; dialog.finished.connect(lambda:self._clear_settings()); dialog.show()
    def _clear_settings(self): self.settings_dialog=None; self.ffmpeg_field=None; self.ffmpeg_status=None; self.ffmpeg_install_button=None
    def detect_ffmpeg(self,line,status):
        found=find_ffmpeg(line.text().strip())
        if found:
            line.setText(found); self.owner.cfg['ffmpeg_path']=found; self.owner.store.save_config(self.owner.cfg)
            status.setText('已检测到 FFmpeg，路径已保存：'+found)
            return found
        line.clear(); self.owner.cfg['ffmpeg_path']=''; self.owner.store.save_config(self.owner.cfg)
        status.setText('未检测到 FFmpeg。点击“安装 FFmpeg”，可通过 winget（Windows）或 Homebrew（macOS）安装。')
        return ''
    def _pick_directory(self,line):
        path=QFileDialog.getExistingDirectory(self.owner,'选择下载目录',line.text())
        if path: line.setText(path)
    def _pick_ffmpeg(self,line):
        name='ffmpeg.exe' if sys.platform=='win32' else 'ffmpeg'
        path=QFileDialog.getOpenFileName(self.owner,'选择 FFmpeg','',f'{name} ({name});;All files (*)')[0]
        if path: line.setText(path)
    def _save_settings(self,dialog,directory,quality,ffmpeg):
        target=directory.text().strip()
        if not target:
            QMessageBox.warning(dialog,'下载设置','请指定视频保存目录。'); return
        ffmpeg_path=ffmpeg.text().strip()
        if ffmpeg_path and not Path(ffmpeg_path).expanduser().is_file():
            QMessageBox.warning(dialog,'FFmpeg 路径无效','指定的 FFmpeg 文件不存在。请重新选择文件，或清空路径使用自动检测。'); return
        if not ffmpeg_path: ffmpeg_path=find_ffmpeg()
        self.owner.cfg.update(download_dir=target,download_quality=quality.currentText(),ffmpeg_path=ffmpeg_path,watch_download=self.auto_box.isChecked(),auto_install_ffmpeg=self.auto_install_box.isChecked())
        self.owner.store.save_config(self.owner.cfg); self.path.setText(target); self.quality.setCurrentText(quality.currentText()); dialog.accept()
        self.output.append('下载设置已保存。'+('边看边下载已开启。' if self.owner.cfg['watch_download'] else '边看边下载已关闭，仍可手动下载。'))
    def queue_current(self,url):
        if not url or url in self.seen: return
        self.seen.add(url)
        if self.process.state()!=QProcess.NotRunning or self.install_process.state()!=QProcess.NotRunning:
            self.queue.append(url); self.output.append('已加入边看边下载队列：'+safe_error(url)); return
        self.url.setText(url); self.start(False)
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
        ffmpeg=find_ffmpeg(self.owner.cfg.get('ffmpeg_path',''))
        if not ffmpeg:
            if self.owner.cfg.get('auto_install_ffmpeg',True): self.install_ffmpeg(target); return
            self.output.append('高清视频合并需要 FFmpeg。请在下载设置中启用自动安装或手动选择 ffmpeg。'); return
        if ffmpeg!=self.owner.cfg.get('ffmpeg_path'):
            self.owner.cfg['ffmpeg_path']=ffmpeg; self.owner.store.save_config(self.owner.cfg)
        try:
            if not self.path.text().strip(): raise ValueError('请选择下载目录')
            directory=Path(self.path.text()).expanduser().resolve(); directory.mkdir(parents=True,exist_ok=True)
            args=download_arguments(target,directory,self.quality.currentText(),playlist,ffmpeg)
        except (OSError,ValueError) as e: self.output.append(str(e)); return
        self.owner.cfg.update(download_dir=str(directory),download_quality=self.quality.currentText()); self.owner.store.save_config(self.owner.cfg)
        self.output.append('开始下载：'+target); self.single.setEnabled(False); self.playlist.setEnabled(False)
        if getattr(sys,'frozen',False): args=['--download-worker',*args[2:]]
        self.process.start(sys.executable,args)
    def read_output(self):
        self.output.append(safe_error(bytes(self.process.readAllStandardOutput()).decode('utf-8',errors='replace')))
    def finished(self,code,status):
        self.single.setEnabled(True); self.playlist.setEnabled(True)
        self.output.append('下载完成。' if code==0 else '下载已停止或失败，查看上方错误。再次下载可续传。')
        if self.queue and self.process.state()==QProcess.NotRunning:
            next_url=self.queue.pop(0); self.url.setText(next_url); self.start(False)
    def install_ffmpeg(self,target='',resume_download=True):
        if self.install_process.state()!=QProcess.NotRunning: return
        if sys.platform=='win32':
            import shutil
            executable=shutil.which('winget')
            args=['install','--exact','--id','Gyan.FFmpeg.Shared','--accept-package-agreements','--accept-source-agreements','--silent']
        elif sys.platform=='darwin':
            executable=shutil.which('brew') or next((p for p in ('/opt/homebrew/bin/brew','/usr/local/bin/brew') if Path(p).exists()),None)
            args=['install','ffmpeg']
        else: executable=None; args=[]
        if not executable:
            if self.ffmpeg_status: self.ffmpeg_status.setText('未找到可用的安装工具。Windows 需要 winget，macOS 需要 Homebrew；也可手动选择 FFmpeg。')
            self.output.append('未检测到可用的系统包管理器。请安装 FFmpeg（ffmpeg.org 下载页列出 Windows/macOS 构建来源），或在下载设置里手动指定。'); return
        self._install_target=target if resume_download else ''; self.output.append('正在通过系统包管理器安装 FFmpeg…')
        if self.ffmpeg_install_button: self.ffmpeg_install_button.setEnabled(False)
        if self.ffmpeg_status: self.ffmpeg_status.setText('FFmpeg 正在安装，请稍候…')
        self.install_process.start(executable,args)
    def ffmpeg_installed(self,code,status):
        if self.ffmpeg_install_button: self.ffmpeg_install_button.setEnabled(True)
        if code:
            if self.ffmpeg_status: self.ffmpeg_status.setText('FFmpeg 安装未完成，请检查系统包管理器后重试。')
            self.output.append('FFmpeg 安装未完成。可以重试，或在下载设置中手动选择 ffmpeg。'); return
        if sys.platform=='darwin':
            for directory in ('/opt/homebrew/bin','/usr/local/bin'):
                if directory not in os.environ.get('PATH',''): os.environ['PATH']=directory+os.pathsep+os.environ.get('PATH','')
        elif sys.platform=='win32':
            links=Path(os.environ.get('LOCALAPPDATA',''))/'Microsoft'/'WinGet'/'Links'
            if links.is_dir() and str(links) not in os.environ.get('PATH',''):
                os.environ['PATH']=str(links)+os.pathsep+os.environ.get('PATH','')
        ffmpeg=find_ffmpeg()
        if ffmpeg:
            self.owner.cfg['ffmpeg_path']=ffmpeg; self.owner.store.save_config(self.owner.cfg)
            if self.ffmpeg_field: self.ffmpeg_field.setText(ffmpeg)
            if self.ffmpeg_status: self.ffmpeg_status.setText('已安装并检测到 FFmpeg，路径已保存：'+ffmpeg)
            self.output.append('FFmpeg 已安装并检测到：'+ffmpeg)
            if self._install_target:
                self.url.setText(self._install_target); self.start(False)
        else:
            if self.ffmpeg_status: self.ffmpeg_status.setText('安装程序已结束，但仍未在 PATH 检测到 FFmpeg。可重启应用后再次检测，或手动选择 ffmpeg。')
            self.output.append('安装程序已结束。若 FFmpeg 不在当前 PATH，请重启应用后重试。')
    def stop(self):
        if self.process.state()!=QProcess.NotRunning: self.process.kill()
        self.queue.clear()
    def closeEvent(self,event):
        # Hide without interrupting downloads; the main window owns the process.
        event.accept()
