import calendar
import json
import weakref
from datetime import date
from pathlib import Path
from PySide6.QtCore import Qt, QUrl, QTimer, QThread, Signal, QDate, QRectF, QSize
from PySide6.QtGui import QColor, QTextCharFormat, QPainter, QPen, QShortcut, QKeySequence, QPixmap, QIcon, QPainterPath, QImageReader, QLinearGradient, QDesktopServices
from PySide6.QtWidgets import (QApplication,QMainWindow,QWidget,QVBoxLayout,QHBoxLayout,QLabel,
    QPushButton,QLineEdit,QTextEdit,QComboBox,QProgressBar,QSplitter,QTabWidget,QCalendarWidget,
    QDialog,QFormLayout,QSpinBox,QDialogButtonBox,QFileDialog,QMessageBox,QTableWidget,QTableWidgetItem,QScrollArea,QGridLayout,QFrame,QStackedWidget,QCheckBox)
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWebEngineCore import QWebEngineProfile,QWebEnginePage,QWebEngineSettings
from .core import Store,Tracker,DEFAULTS
from .sync import sync_pending,GoogleSheets
from .downloads import DownloadDialog
from .capture import CAPTURE_VIDEO_RECT_SCRIPT,seek_video_script
from .security import safe_error,is_youtube_url,validate_sample,valid_video_id

_BACKGROUND_WORKERS=set()

def retain_background_worker(worker):
    _BACKGROUND_WORKERS.add(worker)
    ref=weakref.ref(worker)
    worker.finished.connect(lambda:_BACKGROUND_WORKERS.discard(ref()))

class BrowserPage(QWebEnginePage):
    def __init__(self,*args): super().__init__(*args); self.allow_local_demo=False
    def acceptNavigationRequest(self,url,kind,is_main_frame):
        if url.scheme() in ('http','https'): return True
        if self.allow_local_demo and url.scheme()=='data':
            return True
        return url.toString()=='about:blank'

class QComboBox(QComboBox):
    def __init__(self,*args): super().__init__(*args); self.setFocusPolicy(Qt.StrongFocus)
    def wheelEvent(self,event):
        if self.hasFocus(): super().wheelEvent(event)
        else: event.ignore()

class QSpinBox(QSpinBox):
    def __init__(self,*args): super().__init__(*args); self.setFocusPolicy(Qt.StrongFocus)
    def wheelEvent(self,event):
        if self.hasFocus(): super().wheelEvent(event)
        else: event.ignore()

def category_color(name):
    import hashlib
    hue=int(hashlib.sha256(name.encode('utf-8')).hexdigest()[:8],16)%360
    return QColor.fromHsv(hue,135,210)

def avatar_image(pixmap,size=256,circular=False):
    if pixmap.isNull(): return pixmap
    side=min(pixmap.width(),pixmap.height())
    square=pixmap.copy((pixmap.width()-side)//2,(pixmap.height()-side)//2,side,side)
    square=square.scaled(size,size,Qt.IgnoreAspectRatio,Qt.SmoothTransformation)
    if not circular: return square
    result=QPixmap(size,size); result.fill(Qt.transparent)
    painter=QPainter(result); painter.setRenderHint(QPainter.Antialiasing)
    clip=QPainterPath(); clip.addEllipse(QRectF(0,0,size,size)); painter.setClipPath(clip)
    painter.drawPixmap(0,0,square); painter.end()
    return result

class Worker(QThread):
    result=Signal(object)
    def __init__(self,root,cfg=None): super().__init__(); self.root=root; self.cfg=cfg
    def run(self):
        store=Store(self.root)
        try:
            result=GoogleSheets(self.cfg).categories(self.cfg) if self.cfg else sync_pending(store)
            self.result.emit((True,result))
        except Exception as e: self.result.emit((False,safe_error(e)))
        finally: store.db.close()

class OAuthWorker(QThread):
    result=Signal(object)
    def __init__(self,path): super().__init__(); self.path=path
    def run(self):
        try:
            from .oauth import login
            client_id,email=login(self.path)
            self.result.emit((True,(self.path,client_id,email)))
        except Exception as e: self.result.emit((False,safe_error(e)))

class UpdateWorker(QThread):
    result=Signal(object)
    def run(self):
        try:
            from .updates import latest_release
            self.result.emit((True,latest_release()))
        except Exception as e: self.result.emit((False,safe_error(e)))

class Settings(QDialog):
    def __init__(self,cfg,parent,embedded=False):
        super().__init__(parent); self.owner=parent; self.setWindowTitle('设置与表格映射'); self.resize(600,720); self.fields={}
        layout=QVBoxLayout(self)
        if embedded:
            back=QPushButton('← 返回播放与登记'); back.setObjectName('secondary'); back.clicked.connect(lambda:parent.select_page(0)); layout.addWidget(back); self.back_to_player=back
        else: self.back_to_player=None
        scroll=QScrollArea(); scroll.setWidgetResizable(True); body=QWidget(); form=QFormLayout(body); scroll.setWidget(body); layout.addWidget(scroll)
        labels={'operator':'登记人姓名','mode':'同步模式','credentials':'Google 桌面应用 OAuth JSON','log_id':'日志表 ID','log_sheet':'日志工作表','summary_id':'汇总表 ID','summary_sheet':'汇总工作表', 'date_row':'日期表头行（完整日期）','category_row':'分类表头行','name_col':'姓名列（A=1）','first_person_row':'人员起始行','reflection_header':'观后感栏标题','daily_goal':'每日合格目标','monthly_goal':'月度合格目标','theme':'主题','avatar':'头像符号 / Emoji','mood':'今日心情','log_header_row':'日志表头行','category_sheet':'分类来源工作表（可空）','category_col':'分类来源列'}
        for k,label in labels.items():
            if k=='avatar': k='avatar_path'; label='头像图片'
            sections={'operator':'登记人设置','credentials':'Google 账号连接','log_id':'谷歌表格绑定','date_row':'表格字段映射','daily_goal':'日历与成长目标','theme':'外观与个人资料','watch_download':'下载设置','log_header_row':'日志与分类字段映射'}
            if k in sections:
                heading=QLabel(sections[k]); heading.setStyleSheet('font-size:18px;font-weight:600;padding:18px 0 8px;'); form.addRow(heading)
            v=cfg[k]
            if k=='watch_download':
                widget=QCheckBox('播放时自动下载当前视频'); widget.setChecked(bool(v))
            elif k=='auto_install_ffmpeg':
                widget=QCheckBox('缺少 FFmpeg 时自动安装'); widget.setChecked(bool(v))
            elif k in ('mode','theme','download_quality'):
                widget=QComboBox()
                if k=='mode': widget.addItems(['local','google'])
                elif k=='download_quality': widget.addItems(['720','1080','1440','2160','best'])
                else:
                    for name,code in [('清新绿','sage'),('清新红','rose'),('暗黑','dark')]: widget.addItem(name,code)
                    widget.setCurrentIndex(max(0,widget.findData({'light':'sage'}.get(v,v))))
                if k!='theme': widget.setCurrentText(v)
            elif isinstance(v,int): widget=QSpinBox(); widget.setRange(1,10000); widget.setValue(v)
            else: widget=QLineEdit(str(v))
            self.fields[k]=widget
            if k in ('credentials','avatar_path'):
                widget.setReadOnly(True); widget.setPlaceholderText('未选择 OAuth 桌面应用文件')
                row=QWidget(); line=QHBoxLayout(row); line.setContentsMargins(0,0,0,0); line.addWidget(widget,1)
                choose=QPushButton('选择图片…' if k=='avatar_path' else '选择 OAuth 文件…'); choose.setObjectName('primary'); choose.clicked.connect(self.choose_avatar if k=='avatar_path' else self.choose); line.addWidget(choose)
                if k=='credentials':
                    authorize=QPushButton('连接 Google 账号'); authorize.clicked.connect(self.owner.authorize_google); line.addWidget(authorize)
                if k=='avatar_path': widget.setPlaceholderText('上传 PNG / JPG / WebP 图片')
                form.addRow(label if k=='avatar_path' else '桌面应用 OAuth 配置',row)
                if k=='credentials':
                    self.google_status=QLabel(('已连接 Google 账号：'+cfg.get('oauth_email','')) if cfg.get('oauth_connected') else '尚未连接 Google 账号')
                    self.google_status.setWordWrap(True); form.addRow('账号状态',self.google_status)
            elif k in ('download_dir','ffmpeg_path'):
                row=QWidget(); line=QHBoxLayout(row); line.setContentsMargins(0,0,0,0); line.addWidget(widget,1)
                choose=QPushButton('选择…'); choose.clicked.connect(lambda checked=False,key=k:self.choose_download_path(key)); line.addWidget(choose); form.addRow(label,row)
            elif k in ('watch_download','auto_install_ffmpeg'):
                form.addRow(widget)
            else: form.addRow(label,widget)
        section=QLabel('下载设置'); section.setStyleSheet('font-size:18px;font-weight:600;padding:18px 0 8px;'); form.addRow(section)
        download_button=QPushButton('打开独立下载设置…'); download_button.clicked.connect(parent.open_download_settings); form.addRow(download_button)
        download_status=QLabel('选择边看边下载、画质、保存目录及缺少 FFmpeg 时的安装方式。'); download_status.setWordWrap(True); form.addRow(download_status)
        hint=QLabel('选择桌面应用 OAuth JSON，点击连接并在浏览器中选择 Google 邮箱。令牌保存到系统凭据库。该 Google 账号须能访问目标表格。'); hint.setWordWrap(True); form.addRow(hint)
        update=QPushButton('检查软件更新'); update.clicked.connect(lambda:parent.check_for_updates(manual=True)); form.addRow(update)
        screenshot=QPushButton('截图设置…'); screenshot.clicked.connect(parent.open_screenshot_settings); form.addRow(screenshot)
        buttons=QDialogButtonBox(QDialogButtonBox.Save|QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Save).setText('保存设置'); buttons.button(QDialogButtonBox.Cancel).setText('恢复已保存设置')
        if embedded:
            self.setWindowFlags(Qt.Widget); buttons.accepted.connect(parent.save_settings_page); buttons.rejected.connect(parent.reload_settings_page)
        else: buttons.accepted.connect(self.accept); buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
    def choose(self):
        path,_=QFileDialog.getOpenFileName(self,'选择 Google 桌面应用 OAuth 配置','','JSON (*.json)')
        if path:
            try:
                from .oauth import oauth_client_id
                oauth_client_id(path)
            except (OSError,ValueError) as e:
                QMessageBox.warning(self,'文件不可用',str(e)); return
            self.fields['credentials'].setText(path); self.fields['credentials'].setToolTip(path)
    def choose_download_path(self,key):
        path=QFileDialog.getExistingDirectory(self,'选择下载目录') if key=='download_dir' else QFileDialog.getOpenFileName(self,'选择 FFmpeg','','FFmpeg (ffmpeg.exe ffmpeg)')[0]
        if path: self.fields[key].setText(path)
    def choose_avatar(self):
        path,_=QFileDialog.getOpenFileName(self,'选择头像图片','','图片 (*.png *.jpg *.jpeg *.webp *.bmp)')
        if not path: return
        reader=QImageReader(path); reader.setAutoTransform(True)
        if Path(path).stat().st_size>20*1024*1024:
            QMessageBox.warning(self,'图片过大','请选择小于 20 MB 的头像'); return
        dimensions=reader.size()
        if not dimensions.isValid() or dimensions.width()*dimensions.height()>40_000_000:
            QMessageBox.warning(self,'图片过大','请选择总像素不超过 4000 万的头像'); return
        reader.setAllocationLimit(128)
        pixmap=QPixmap.fromImage(reader.read())
        if pixmap.isNull(): QMessageBox.warning(self,'无法读取','请选择有效的图片文件。'); return
        # Copy into app storage so moving the source image will not break the avatar.
        import uuid
        destination=self.owner.store.root/'avatars'; destination.mkdir(exist_ok=True)
        target=destination/(uuid.uuid4().hex+'.png')
        if not avatar_image(pixmap).save(str(target),'PNG'):
            QMessageBox.warning(self,'保存失败','头像文件无法保存。'); return
        self.fields['avatar_path'].setText(str(target.resolve()))
    def values(self):
        return {k:(w.value() if isinstance(w,QSpinBox) else w.isChecked() if isinstance(w,QCheckBox) else w.currentData() if k=='theme' else w.currentText() if isinstance(w,QComboBox) else w.text().strip()) for k,w in self.fields.items()}

class HabitCalendar(QCalendarWidget):
    def __init__(self):
        super().__init__(); self.days={}; self.goal=2
        self.setVerticalHeaderFormat(QCalendarWidget.NoVerticalHeader)
        self.setHorizontalHeaderFormat(QCalendarWidget.ShortDayNames)
        self.setGridVisible(False)
    def paintCell(self,p,rect,d):
        p.save(); p.setRenderHint(QPainter.Antialiasing)
        if d.month()!=self.monthShown(): p.restore(); return
        color='#58ba83' if self.days.get(d.toString('yyyy-MM-dd'),0)>=self.goal else '#d06a70' if d<=QDate.currentDate() else '#42454b'
        center=rect.center(); size=min(26,rect.height()-5)
        p.setPen(Qt.NoPen); p.setBrush(QColor(color)); p.drawEllipse(QRectF(center.x()-size/2,center.y()-size/2,size,size))
        if d==QDate.currentDate():
            p.setBrush(Qt.NoBrush); p.setPen(QPen(QColor('#d9eade'),1.5)); p.drawEllipse(QRectF(center.x()-size/2-2,center.y()-size/2-2,size+4,size+4))
        p.setPen(QColor('#ffffff')); p.drawText(rect,Qt.AlignCenter,str(d.day())); p.restore()

class Sapling(QWidget):
    def __init__(self): super().__init__(); self.health=100; self.level=1; self.setMinimumSize(130,150)
    def paintEvent(self,event):
        p=QPainter(self); p.setRenderHint(QPainter.Antialiasing); p.translate(self.width()/2,self.height()-20)
        scale=min(self.width()/170,self.height()/180); p.scale(scale,scale)
        leaves=min(10,2*self.level); stem=35+min(self.level-1,4)*23
        shadow=QLinearGradient(-40,0,40,0); shadow.setColorAt(0,QColor('#15171a')); shadow.setColorAt(.5,QColor('#101113')); shadow.setColorAt(1,QColor('#202226'))
        p.setPen(Qt.NoPen); p.setBrush(shadow); p.drawEllipse(QRectF(-42,-4,84,12))
        p.setPen(QPen(QColor('#668840'),3)); trunk=QPainterPath(); trunk.moveTo(0,-28); trunk.cubicTo(-5,-40,6,-stem,0,-28-stem); p.drawPath(trunk)
        for i in range(leaves):
            y=-42-i*(stem-10)/max(1,leaves-1); side=1 if i%2 else -1
            p.setPen(QPen(QColor('#6e9750'),2)); p.drawLine(0,y,side*27,y-16)
            p.save(); p.translate(side*24,y-17); p.rotate(side*30)
            leaf=QPainterPath(); leaf.moveTo(-19,0); leaf.cubicTo(-8,-17,14,-13,23,0); leaf.cubicTo(10,13,-10,14,-19,0)
            gradient=QLinearGradient(0,-12,0,12); gradient.setColorAt(0,QColor('#a1d66a' if self.health>=60 else '#c0aa66')); gradient.setColorAt(.45,QColor('#659d3c')); gradient.setColorAt(1,QColor('#2d612b'))
            p.setPen(QPen(QColor('#47702f'),.6)); p.setBrush(gradient); p.drawPath(leaf)
            p.setPen(QPen(QColor('#b5cf80'),.7)); p.drawLine(-16,0,20,0)
            for vx in (-8,0,8): p.drawLine(vx,0,vx+5,-6); p.drawLine(vx,0,vx+5,6)
            p.restore()
        pot=QPainterPath(); pot.moveTo(-27,-28); pot.lineTo(27,-28); pot.lineTo(20,1); pot.quadTo(0,8,-20,1); pot.closeSubpath()
        clay=QLinearGradient(-28,0,28,0); clay.setColorAt(0,QColor('#86503a')); clay.setColorAt(.3,QColor('#d59b73')); clay.setColorAt(1,QColor('#95563e'))
        p.setPen(Qt.NoPen); p.setBrush(clay); p.drawPath(pot); p.drawRoundedRect(QRectF(-30,-35,60,11),3,3)
        p.setBrush(QColor('#51382b')); p.drawEllipse(QRectF(-26,-36,52,9)); p.setBrush(QColor('#997451'))
        for sx in (-18,-9,2,13): p.drawEllipse(QRectF(sx,-33,2,1))

class Chart(QWidget):
    def __init__(self): super().__init__(); self.days={}; self.series={}; self.month=date.today().strftime('%Y-%m'); self.setMinimumHeight(125)
    def paintEvent(self,event):
        p=QPainter(self); p.setRenderHint(QPainter.Antialiasing); p.setPen(QColor('#8b9bb4')); p.drawText(10,20,'每日合格数量')
        n=calendar.monthrange(int(self.month[:4]),int(self.month[5:]))[1]; w=self.width()-60; h=self.height()-95
        series=self.series or {'合格总数':self.days}; peak=max(2,max((v for days in series.values() for v in days.values()),default=0))
        p.drawLine(35,55+h,35+w,55+h)
        for tick in range(peak+1):
            if peak>10 and tick%max(1,peak//5): continue
            p.setPen(QColor('#8b9bb4')); p.drawText(5,int(60+h-tick*h/peak),str(tick))
        x=15
        for name,days in series.items():
            color=category_color(name); p.setPen(color); p.drawText(x,40,name); x+=p.fontMetrics().horizontalAdvance(name)+25
            vals=[days.get(f'{self.month}-{i:02}',0) for i in range(1,n+1)]; p.setPen(QPen(color,2))
            limit=date.today().day if self.month==date.today().strftime('%Y-%m') else n
            for i in range(1,limit): p.drawLine(35+(i-1)*w/(n-1),55+h-vals[i-1]*h/peak,35+i*w/(n-1),55+h-vals[i]*h/peak)
        p.drawText(15,self.height()-5,'1'); p.drawText(self.width()-30,self.height()-5,str(n))

class ReviewChart(QWidget):
    def __init__(self,kind):
        super().__init__(); self.kind=kind; self.rows=[]; self.month=date.today().strftime('%Y-%m'); self.setMinimumHeight(250)
    def paintEvent(self,event):
        p=QPainter(self); p.setRenderHint(QPainter.Antialiasing); p.setPen(QColor('#97a4af'))
        if not self.rows:
            p.drawText(self.rect(),Qt.AlignCenter,'本月暂无登记数据，完成观看后在这里复盘。'); return
        if self.kind=='categories':
            counts={}
            for row in self.rows: counts[row['category']]=counts.get(row['category'],0)+1
            counts=sorted(counts.items(),key=lambda x:-x[1]); colors=['#65b885','#65add0','#d5aa66','#b68aca','#cf737c']
            if len(counts)>7: counts=counts[:6]+[('其他',sum(n for _,n in counts[6:]))]
            size=min(self.height()-50,self.width()*.42); x=20; y=(self.height()-size)/2; angle=90*16
            for i,(name,n) in enumerate(counts):
                span=round(n/len(self.rows)*360*16); p.setPen(Qt.NoPen); p.setBrush(category_color(name)); p.drawPie(QRectF(x,y,size,size),angle,-span); angle-=span
                p.setPen(category_color(name)); p.drawText(int(size+45),30+i*24,f'{name}  {n} 次 · {n/len(self.rows):.0%}')
        else:
            n=calendar.monthrange(int(self.month[:4]),int(self.month[5:]))[1]; w=self.width()-70; h=self.height()-60; last=None
            p.setPen(QColor('#56606b')); p.drawLine(45,25+h,45+w,25+h)
            for percent in (0,50,100):
                yy=25+h-percent*h/100; p.drawText(2,int(yy+5),f'{percent}%')
            for day in range(1,n+1):
                records=[r for r in self.rows if r['timestamp'][8:10]==f'{day:02}']
                if not records: last=None; continue
                rate=sum(r['ratio']>=.95 for r in records)/len(records); x=45+(day-1)*w/(n-1); y=25+h-rate*h
                p.setPen(QPen(QColor('#65add0'),2))
                if last: p.drawLine(*last,x,y)
                p.setBrush(QColor('#65add0')); p.drawEllipse(QRectF(x-4,y-4,8,8)); last=(x,y)
            p.drawText(45,self.height()-8,'1 日'); p.drawText(self.width()-55,self.height()-8,f'{n} 日')

class Window(QMainWindow):
    def __init__(self,root,offline=False):
        super().__init__(); self.store=Store(root); self.cfg=self.store.config(); self.tracker=Tracker(); self.worker=None; self.oauth_worker=None; self.offline=offline
        self.setWindowTitle('静心 · 视频学习与灵修'); self.resize(1420,930)
        icon=QIcon(str(Path(__file__).resolve().parents[1]/'assets'/'devotionflow.png'))
        self.setWindowIcon(icon)
        outer=QWidget(); layout=QVBoxLayout(outer); self.setCentralWidget(outer)
        bar=QHBoxLayout(); brand=QLabel(); brand.setPixmap(QPixmap(str(Path(__file__).resolve().parents[1]/'assets'/'devotionflow.png')).scaled(40,40,Qt.KeepAspectRatio,Qt.SmoothTransformation)); bar.addWidget(brand); title=QLabel('静心片刻，让所见成为成长'); title.setStyleSheet('font-size:20px;font-weight:600'); bar.addWidget(title); bar.addStretch()
        for title,callback in [('打开 YouTube',self.open_youtube),('切换主题',self.toggle_theme),('设置',self.settings),('重试同步',self.sync)]:
            b=QPushButton(title); b.clicked.connect(callback); bar.addWidget(b)
        layout.addLayout(bar); self.banner=QLabel(); layout.addWidget(self.banner)
        split=QSplitter(); layout.addWidget(split,1); left=QWidget(); ll=QVBoxLayout(left); nav=QHBoxLayout()
        self.browser=QWebEngineView(); self.profile=QWebEngineProfile('devotion',self.browser)
        self.profile.setPersistentStoragePath(str(Path(root).resolve()/'browser'))
        self.profile.setCachePath(str(Path(root).resolve()/'browser-cache'))
        self.profile.setPersistentCookiesPolicy(QWebEngineProfile.ForcePersistentCookies)
        self.profile.setHttpAcceptLanguage('zh-CN,zh;q=0.9,en;q=0.7')
        self.browser.setPage(BrowserPage(self.profile,self.browser))
        for attribute in (QWebEngineSettings.LocalContentCanAccessFileUrls,QWebEngineSettings.LocalContentCanAccessRemoteUrls,QWebEngineSettings.JavascriptCanAccessClipboard,QWebEngineSettings.JavascriptCanPaste):
            self.browser.settings().setAttribute(attribute,False)
        self.address=QLineEdit('https://www.youtube.com'); self.address.returnPressed.connect(self.navigate)
        for title,fn in [('←',self.browser.back),('↻',self.browser.reload)]:
            b=QPushButton(title); b.clicked.connect(fn); nav.addWidget(b)
        nav.addWidget(self.address); ll.addLayout(nav); ll.addWidget(self.browser); split.addWidget(left)
        self.browser.urlChanged.connect(lambda u:self.address.setText(u.toString() if u.scheme() in ('http','https') else 'https://www.youtube.com'))
        tabs=QTabWidget(); split.addWidget(tabs); split.setSizes([940,450]); tabs.setMinimumWidth(390)
        watch=QWidget(); form=QVBoxLayout(watch); tabs.addTab(watch,'观看登记')
        self.title=QLabel('打开视频，开始今天的学习'); self.title.setWordWrap(True); self.title.setStyleSheet('font-size:21px;font-weight:600'); form.addWidget(self.title)
        self.metrics=QLabel('等待视频'); form.addWidget(self.metrics); self.progress=QProgressBar(); form.addWidget(self.progress)
        self.category=QComboBox(); self.category.setEditable(True); form.addWidget(QLabel('视频分类')); form.addWidget(self.category)
        refresh=QPushButton('读取在线历史分类'); refresh.clicked.connect(self.categories); form.addWidget(refresh); self.category_refresh_button=refresh
        self.reflection=QTextEdit(); self.reflection.setPlaceholderText('今天有哪些触动？记录你的认识与感想（选填）'); form.addWidget(self.reflection)
        self.submit=QPushButton('确认登记并同步表格'); self.submit.setMinimumHeight(46); self.submit.clicked.connect(self.register); form.addWidget(self.submit)
        reset=QPushButton('开始新一轮观看'); reset.clicked.connect(self.new_round); form.addWidget(reset)
        self.status=QLabel('登记后先保存本地，再同步。'); self.status.setWordWrap(True); form.addWidget(self.status); form.addStretch()
        habit=QWidget(); hl=QVBoxLayout(habit); tabs.addTab(habit,'成长看板')
        self.tree=QLabel(); self.tree.setWordWrap(True); self.tree.setStyleSheet('font-size:22px'); hl.addWidget(self.tree)
        moodrow=QHBoxLayout(); self.mood=QComboBox(); self.mood.addItems(['平静','感恩','喜悦','疲惫','低落']); self.mood.setCurrentText(self.cfg['mood']); self.mood.currentTextChanged.connect(self.save_mood); moodrow.addWidget(QLabel('今日心情')); moodrow.addWidget(self.mood); hl.addLayout(moodrow)
        self.calendar=HabitCalendar(); self.calendar.currentPageChanged.connect(self.refresh); hl.addWidget(self.calendar)
        self.summary=QLabel(); self.summary.setWordWrap(True); hl.addWidget(self.summary); self.chart=Chart(); hl.addWidget(self.chart); hl.addStretch()
        self.history=QTableWidget(0,5); self.history.setHorizontalHeaderLabels(['时间','视频','完播率','模式/状态','错误']); self.history.setEditTriggers(QTableWidget.NoEditTriggers); tabs.addTab(self.history,'登记记录')
        # Present the journal, calendar and growth together, as in the reference.
        tabs.removeTab(tabs.indexOf(habit))
        dashboard=QWidget(); dl=QVBoxLayout(dashboard); dl.setContentsMargins(16,8,8,8); dl.setSpacing(14)
        heading=QLabel('灵修成长看板'); heading.setObjectName('heading'); dl.addWidget(heading)
        self.welcome=QLabel(); self.welcome.setObjectName('welcome'); dl.addWidget(self.welcome)
        def card(title):
            box=QFrame(); box.setObjectName('card'); content=QVBoxLayout(box); content.setContentsMargins(16,12,16,12)
            label=QLabel(title); label.setObjectName('eyebrow'); content.addWidget(label); return box,content
        grid=QGridLayout(); grid.setSpacing(12); dl.addLayout(grid)
        calbox,cl=card('习惯日历  /  HABIT TRACKER'); cl.addWidget(self.calendar); self.calendar.setMinimumWidth(270); self.calendar.setFixedHeight(235); grid.addWidget(calbox,0,0)
        plantbox,pl=card('小树成长'); self.plant=Sapling(); pl.addWidget(self.plant); pl.addWidget(self.tree); self.tree.setStyleSheet('font-size:12px;'); self.healthbar=QProgressBar(); self.healthbar.setFixedHeight(7); self.healthbar.setTextVisible(False); pl.addWidget(self.healthbar); grid.addWidget(plantbox,0,1)
        analysis,al=card('月度数据  /  MONTHLY ANALYTICS'); self.statline=QLabel(); self.statline.setObjectName('statline'); al.addWidget(self.statline); al.addWidget(self.chart); al.addWidget(self.summary); dl.addWidget(analysis)
        goals,gl=card('今日目标'); self.dailybar=QProgressBar(); gl.addWidget(self.dailybar); mr=QHBoxLayout(); mr.addWidget(QLabel('此刻的心情')); mr.addWidget(self.mood); gl.addLayout(mr); dl.addWidget(goals)
        dl.addStretch(); split.addWidget(dashboard); tabs.setParent(None)
        journal, jl=card('观看笔记  /  JOURNAL'); jl.addWidget(self.title); jl.addWidget(self.metrics); jl.addWidget(self.progress)
        cr=QHBoxLayout(); cr.addWidget(QLabel('分类')); cr.addWidget(self.category,1); cr.addWidget(refresh); jl.addLayout(cr)
        self.reflection.setFixedHeight(75); jl.addWidget(self.reflection)
        actions=QHBoxLayout(); self.submit.setObjectName('primary'); actions.addWidget(self.submit,1); actions.addWidget(reset); jl.addLayout(actions); jl.addWidget(self.status); ll.addWidget(journal)
        self.browser.setMinimumHeight(300); ll.setStretch(1,1)
        self.history_dialog=QDialog(self); self.history_dialog.setWindowTitle('登记记录'); self.history_dialog.resize(950,550); QVBoxLayout(self.history_dialog).addWidget(self.history)
        history_button=QPushButton('查看全部登记记录'); history_button.clicked.connect(self.history_dialog.show); dl.addWidget(history_button)
        split.setSizes([790,610]); dashboard.setMinimumWidth(560); self.resize(1480,960)
        self.browser.loadStarted.connect(lambda:self.browser_status.setText('正在加载 YouTube…'))
        self.browser.loadFinished.connect(self.loaded)
        self.browser_status=QLabel('内嵌 YouTube · 可搜索、登录及播放'); ll.insertWidget(1,self.browser_status)
        self.build_pages(layout,bar,split,left,ll,nav,journal,jl,dashboard,analysis,goals,brand)
        self.probe=Path(__file__).with_name('probe.js').read_text('utf-8'); self.timer=QTimer(self); self.timer.timeout.connect(self.poll); self.timer.start(500)
        self.retry=QTimer(self); self.retry.timeout.connect(self.sync); self.retry.start(60000)
        self.apply_theme(); self.refresh()
        for label in self.findChildren(QLabel): label.setTextFormat(Qt.PlainText)
        self.resume_position=None; self.draft_loading=False
        self.download_dialog=DownloadDialog(self)
        self.update_worker=None
        self._screenshot_pending=False
        self.screenshot_timer=QTimer(self); self.screenshot_timer.timeout.connect(self.capture_scheduled_screenshot)
        if self.cfg.get('screenshot_interval',0): self.screenshot_timer.start(self.cfg['screenshot_interval']*1000)
        self.draft_timer=QTimer(self); self.draft_timer.setSingleShot(True); self.draft_timer.timeout.connect(self.save_draft)
        self.reflection.textChanged.connect(self.schedule_draft); self.category.currentTextChanged.connect(self.schedule_draft)
        self.autosave=QTimer(self); self.autosave.timeout.connect(self.save_draft); self.autosave.start(1000)
        if offline: self.demo()
        else:
            saved=self.store.load_state('last:'+self.draft_scope())
            if saved and valid_video_id(saved):
                self.restore_draft(saved); self.browser.setUrl(QUrl('https://www.youtube.com/watch?v='+saved))
                self.status.setText('已恢复上次视频、观看进度、分类和感想。')
            else: self.browser.setUrl(QUrl('https://www.youtube.com/?hl=zh-CN'))
            QTimer.singleShot(3500,self.check_for_updates)
    def draft_scope(self): return self.cfg['mode']+':'+self.cfg['operator']
    def schedule_draft(self,*args):
        if not self.draft_loading: self.draft_timer.start(350)
    def save_draft(self):
        if self.draft_loading or not self.tracker.video or self.tracker.video=='local-demo': return
        self.store.save_state('draft:'+self.draft_scope()+':'+self.tracker.video,dict(tracker=self.tracker.snapshot(),category=self.category.currentText(),reflection=self.reflection.toPlainText()))
        self.store.save_state('last:'+self.draft_scope(),self.tracker.video)
    def restore_draft(self,video):
        saved=self.store.load_state('draft:'+self.draft_scope()+':'+video)
        self.draft_loading=True; self.tracker=Tracker(); self.tracker.video=video
        if saved:
            try: self.tracker.restore(saved['tracker'])
            except (ValueError,TypeError,KeyError):
                self.status.setText('保存的播放记录无效，已从头开始。'); self.draft_loading=False; self.resume_position=None; return
            self.tracker.registered=self.tracker.registered or self.store.has_record(self.tracker.round_id)
            self.category.setCurrentText(saved['category']); self.reflection.setPlainText(saved['reflection'])
            self.resume_position=self.tracker.position
        else: self.reflection.clear(); self.resume_position=None
        self.draft_loading=False
    def screenshot(self):
        self.capture_video_frame(automatic=False)
    def capture_scheduled_screenshot(self):
        self.capture_video_frame(automatic=True)
    def capture_video_frame(self,automatic):
        if self._screenshot_pending: return
        if not is_youtube_url(self.browser.url().toString()):
            if not automatic: self.status.setText('请先在 YouTube 打开一个视频，再进行截图。')
            return
        self._screenshot_pending=True
        self.browser.page().runJavaScript(CAPTURE_VIDEO_RECT_SCRIPT,lambda rect:self.save_video_frame(rect,automatic))
    def save_video_frame(self,rect,automatic):
        if isinstance(rect,str):
            try: rect=json.loads(rect)
            except (TypeError,json.JSONDecodeError): rect=None
        if not isinstance(rect,dict) or not all(isinstance(rect.get(k),(int,float)) for k in ('x','y','w','h')):
            self._screenshot_pending=False
            if not automatic:
                detail=rect.get('message','') if isinstance(rect,dict) else ''
                self.status.setText('没有找到可截取的视频画面。请确认视频已开始播放后重试；若播放器刚打开，可等待几秒。'+(('（'+detail+'）') if detail else ''))
            return
        if automatic and not rect.get('playing'):
            self._screenshot_pending=False; return
        QTimer.singleShot(120,lambda:self._save_video_frame_now(rect,automatic))
    def _save_video_frame_now(self,rect,automatic):
        self._screenshot_pending=False
        viewport=self.browser
        pixmap=viewport.grab()
        scale=pixmap.width()/max(1,viewport.width())
        x=max(0,round(rect['x']*scale)); y=max(0,round(rect['y']*scale))
        w=min(pixmap.width()-x,round(rect['w']*scale)); h=min(pixmap.height()-y,round(rect['h']*scale))
        if w<=0 or h<=0:
            if not automatic: self.status.setText('视频区域当前不可见，无法截图。')
            return
        image=pixmap.copy(x,y,w,h)
        from datetime import datetime
        directory=Path(self.cfg.get('screenshot_dir') or (self.store.root/'screenshots')).expanduser()
        try:
            directory.mkdir(parents=True,exist_ok=True)
            video_id=(self.tracker.video or 'youtube')[:128]
            stamp=datetime.now().astimezone().strftime('%Y%m%d-%H%M%S-%f')
            path=directory/f'{stamp}-{video_id}.png'
            if not image.save(str(path),'PNG'): raise OSError('PNG 保存失败')
            self.status.setText(('定时截图已保存：' if automatic else '视频截图已保存：')+str(path))
        except OSError as error: self.status.setText('截图保存失败：'+safe_error(error))
    def open_screenshot_settings(self):
        dialog=QDialog(self); dialog.setWindowTitle('截图设置'); dialog.resize(540,220); form=QVBoxLayout(dialog)
        enabled=QCheckBox('播放期间定时自动截取视频画面'); enabled.setChecked(bool(self.cfg.get('screenshot_interval',0))); form.addWidget(enabled)
        seconds=QComboBox(); seconds.addItems(['5','10','15','30','60']); seconds.setCurrentText(str(self.cfg.get('screenshot_interval') or 5)); form.addWidget(QLabel('截取间隔（秒）')); form.addWidget(seconds)
        row=QHBoxLayout(); path=QLineEdit(self.cfg.get('screenshot_dir') or str(self.store.root/'screenshots')); choose=QPushButton('选择目录…')
        choose.clicked.connect(lambda:self.choose_screenshot_directory(path)); row.addWidget(QLabel('保存目录')); row.addWidget(path,1); row.addWidget(choose); form.addLayout(row)
        hint=QLabel('手动截图按钮会直接保存当前 YouTube 视频区域，不包含网页周围内容或播放器控件。定时截图仅在播放时保存。'); hint.setWordWrap(True); form.addWidget(hint)
        buttons=QDialogButtonBox(QDialogButtonBox.Save|QDialogButtonBox.Cancel); buttons.accepted.connect(lambda:self.save_screenshot_settings(dialog,enabled,seconds,path)); buttons.rejected.connect(dialog.reject); form.addWidget(buttons); dialog.exec()
    def choose_screenshot_directory(self,line):
        selected=QFileDialog.getExistingDirectory(self,'选择截图保存目录',line.text())
        if selected: line.setText(selected)
    def save_screenshot_settings(self,dialog,enabled,seconds,path):
        directory=path.text().strip()
        if not directory: QMessageBox.warning(dialog,'截图设置','请选择截图保存目录。'); return
        interval=int(seconds.currentText()) if enabled.isChecked() else 0
        self.cfg.update(screenshot_dir=directory,screenshot_interval=interval); self.store.save_config(self.cfg)
        if interval: self.screenshot_timer.start(interval*1000)
        else: self.screenshot_timer.stop()
        dialog.accept(); self.status.setText('截图设置已保存。'+(f'播放时每 {interval} 秒自动截图。' if interval else '自动截图已关闭；仍可手动截图。'))
    def open_downloads(self): self.download_dialog.present(self.browser.url().toString())
    def open_download_settings(self):
        self.download_dialog.open_settings()
    def authorize_google(self):
        if self.oauth_worker and self.oauth_worker.isRunning(): return
        path=self.settings_page.fields['credentials'].text().strip()
        try:
            from .oauth import oauth_client_id
            oauth_client_id(path)
        except (OSError,ValueError) as e:
            QMessageBox.warning(self,'Google 登录设置',str(e)); return
        self.status.setText('正在打开默认浏览器，请登录并批准 DevotionFlow 访问 Google Sheets。')
        self.settings_page.google_status.setText('浏览器授权完成后，正在保存并验证系统凭据库中的登录令牌…')
        self.cfg.update(credentials=path,oauth_client_file=path); self.store.save_config(self.cfg)
        self.category_refresh_button.setEnabled(False)
        self.oauth_worker=OAuthWorker(path); self.oauth_worker.result.connect(self.google_authorized); retain_background_worker(self.oauth_worker); self.oauth_worker.start()
    def check_for_updates(self,manual=False):
        if self.update_worker and self.update_worker.isRunning(): return
        if not manual and self.cfg.get('last_update_check')==date.today().isoformat(): return
        if not manual:
            self.cfg['last_update_check']=date.today().isoformat(); self.store.save_config(self.cfg)
        self._manual_update_check=manual
        self.update_worker=UpdateWorker(); self.update_worker.result.connect(self.update_checked); retain_background_worker(self.update_worker); self.update_worker.start()
    def update_checked(self,result):
        ok,value=result; manual=self._manual_update_check
        if not ok:
            if manual: QMessageBox.warning(self,'检查更新','暂时无法检查更新：'+str(value))
            return
        if not value:
            if manual:
                from .updates import VERSION
                QMessageBox.information(self,'检查更新',f'当前已是最新版本（{VERSION}）。')
            return
        from .updates import VERSION
        answer=QMessageBox.question(self,'发现新版本',f'当前版本：{VERSION}\n发现版本：{value["version"]}\n\n打开 DevotionFlow 官方发布页下载对应系统安装包吗？',QMessageBox.Yes|QMessageBox.No,QMessageBox.Yes)
        if answer==QMessageBox.Yes: QDesktopServices.openUrl(QUrl(value['url']))
    def google_authorized(self,result):
        ok,value=result
        self.category_refresh_button.setEnabled(True)
        if not ok:
            self.settings_page.google_status.setText('Google 账号未连接：'+str(value))
            self.status.setText('Google 授权失败：'+str(value)); return
        path,client_id,email=value
        self.cfg.update(mode='google',credentials=path,oauth_client_file=path,oauth_connected=True,oauth_email=email)
        self.settings_page.fields['credentials'].setText(path)
        self.settings_page.fields['mode'].setCurrentText('google'); self.store.save_config(self.cfg); self.refresh()
        self.settings_page.google_status.setText('已连接 Google 账号：'+email+'（登录令牌已从系统凭据库读回验证）')
        self.status.setText('已连接 Google 账号：'+email+'。该账号须有目标表格访问权限。'); self.sync()
    def build_pages(self,layout,bar,split,left,ll,nav,journal,jl,dashboard,analysis,goals,brand):
        self.fullscreen_active=False
        # A persistent browser stays alive while other pages are selected.
        layout.removeItem(bar); bar.setParent(None)
        self.topbar=QWidget(); self.topbar.setLayout(bar); layout.insertWidget(0,self.topbar)
        self.avatar=QPushButton(); self.avatar.setFixedSize(48,42); self.avatar.clicked.connect(lambda:self.select_page(1)); bar.addWidget(self.avatar)
        self.brand_icon=brand
        self.sidebar_toggle=QPushButton('☰'); self.sidebar_toggle.setToolTip('收起 / 展开导航栏'); self.sidebar_toggle.clicked.connect(self.toggle_sidebar); bar.insertWidget(0,self.sidebar_toggle)
        layout.removeWidget(split)
        body=QHBoxLayout(); layout.addLayout(body,1)
        self.sidebar=QFrame(); self.sidebar.setFixedWidth(175); sl=QVBoxLayout(self.sidebar); sl.setContentsMargins(8,20,8,12)
        sl.addWidget(QLabel('DEVOTION FLOW')); sl.addSpacing(24); self.nav_buttons=[]
        self.pages=QStackedWidget(); body.addWidget(self.sidebar); body.addWidget(self.pages,1)
        for i,name in enumerate(['▶  播放与登记','▦  日历与小树','◷  数据分析','⚙  系统设置']):
            button=QPushButton(name); button.setCheckable(True); button.setMinimumHeight(48); button.clicked.connect(lambda checked=False,index=i:self.select_page(index)); sl.addWidget(button); self.nav_buttons.append(button)
        sl.addStretch(); sl.addWidget(QLabel('专注每一次成长'))
        dashboard.setMinimumWidth(0); dashboard.setParent(None); split.setParent(self.pages); self.pages.addWidget(split)
        # Quick log goes beside the full-height browser, rather than below it.
        ll.removeWidget(journal); split.addWidget(journal); journal.setMinimumWidth(290); journal.setMaximumWidth(370); self.quicklog=journal
        self.reflection.setMinimumHeight(120); self.reflection.setMaximumHeight(220); jl.addStretch(1)
        split.setSizes([1000,320]); self.browser.setMinimumHeight(0)
        ll.removeItem(nav); nav.setParent(None)
        self.player_nav=QWidget(); self.player_nav.setLayout(nav); ll.insertWidget(0,self.player_nav)
        full=QPushButton('全屏  F11'); full.clicked.connect(self.toggle_fullscreen); nav.addWidget(full)
        for name,callback in [('截图',self.screenshot),('下载设置',self.open_download_settings),('下载当前视频',self.open_downloads)]:
            button=QPushButton(name); button.clicked.connect(callback); nav.addWidget(button)
        exitbutton=QPushButton('退出全屏  Esc',self.browser); exitbutton.clicked.connect(self.exit_fullscreen); exitbutton.move(18,18); exitbutton.hide(); self.exitbutton=exitbutton
        self.browser.settings().setAttribute(QWebEngineSettings.FullScreenSupportEnabled,True)
        self.browser.page().fullScreenRequested.connect(self.web_fullscreen)
        self.f11=QShortcut(QKeySequence('F11'),self); self.f11.activated.connect(self.toggle_fullscreen)
        self.esc=QShortcut(QKeySequence('Escape'),self); self.esc.activated.connect(self.exit_fullscreen)
        dashboard.layout().removeWidget(analysis); analysis.setParent(None)
        self.pages.addWidget(dashboard); self.calendar.setFixedHeight(360); self.plant.setMinimumHeight(260)
        self.day_details=QLabel(); self.day_details.setWordWrap(True); dashboard.layout().insertWidget(3,self.day_details)
        self.calendar.selectionChanged.connect(self.selected_day)
        analytics=QWidget(); av=QVBoxLayout(analytics); title=QLabel('数据分析与复盘'); title.setObjectName('heading'); av.addWidget(title)
        monthbar=QHBoxLayout(); monthbar.addWidget(QLabel('查看月份')); self.analytics_month=QComboBox(); self.analytics_month.currentTextChanged.connect(self.refresh_analytics); monthbar.addWidget(self.analytics_month); monthbar.addStretch(); av.addLayout(monthbar)
        av.addWidget(analysis); self.chart.setMinimumHeight(250)
        charts=QHBoxLayout(); self.category_chart=ReviewChart('categories'); self.trend_chart=ReviewChart('trend')
        for title,widget in [('分类占比（登记次数）',self.category_chart),('每日完播达标率（≥95%的登记占比）',self.trend_chart)]:
            box=QFrame(); box.setObjectName('card'); bv=QVBoxLayout(box); bv.addWidget(QLabel(title)); bv.addWidget(widget); charts.addWidget(box)
        av.addLayout(charts); av.addStretch(); self.pages.addWidget(analytics)
        self.settings_page=Settings(self.cfg,self,embedded=True); self.pages.addWidget(self.settings_page)
        self.select_page(0)
        self.sidebar.setVisible(not self.cfg['sidebar_collapsed'])
    def toggle_sidebar(self):
        self.cfg['sidebar_collapsed']=not self.cfg['sidebar_collapsed']; self.sidebar.setVisible(not self.cfg['sidebar_collapsed']); self.store.save_config(self.cfg)
    def select_page(self,index):
        self.pages.setCurrentIndex(index)
        for i,button in enumerate(self.nav_buttons): button.setChecked(i==index)
    def save_settings_page(self):
        self.save_draft(); old_scope=self.draft_scope()
        self.cfg.update(self.settings_page.values()); self.store.save_config(self.cfg); self.apply_theme(); self.refresh(); self.banner.setText('设置已保存 · '+self.banner.text())
        if old_scope!=self.draft_scope() and self.tracker.video: self.restore_draft(self.tracker.video)
    def reload_settings_page(self):
        for key,widget in self.settings_page.fields.items():
            value=self.cfg[key]
            if isinstance(widget,QSpinBox): widget.setValue(value)
            elif isinstance(widget,QCheckBox): widget.setChecked(bool(value))
            elif isinstance(widget,QComboBox):
                if key=='theme': widget.setCurrentIndex(max(0,widget.findData({'light':'sage'}.get(value,value))))
                else: widget.setCurrentText(value)
            else: widget.setText(str(value))
    def toggle_fullscreen(self):
        if self.fullscreen_active: self.exit_fullscreen()
        else: self.enter_fullscreen()
    def enter_fullscreen(self):
        if self.fullscreen_active: return
        self.was_maximized=self.isMaximized(); self.fullscreen_active=True; self.select_page(0)
        for widget in (self.topbar,self.sidebar,self.banner,self.quicklog,self.player_nav,self.browser_status): widget.hide()
        self.showFullScreen(); self.exitbutton.show(); self.exitbutton.raise_()
    def exit_fullscreen(self):
        if not self.fullscreen_active: return
        self.browser.page().runJavaScript('if(document.fullscreenElement) document.exitFullscreen();')
        self.fullscreen_active=False; self.exitbutton.hide()
        for widget in (self.topbar,self.sidebar,self.banner,self.quicklog,self.player_nav,self.browser_status): widget.show()
        self.sidebar.setVisible(not self.cfg['sidebar_collapsed'])
        if self.was_maximized: self.showMaximized()
        else: self.showNormal()
    def web_fullscreen(self,request):
        request.accept()
        if request.toggleOn(): self.enter_fullscreen()
        else: self.exit_fullscreen()
    def selected_day(self):
        day=self.calendar.selectedDate().toString('yyyy-MM-dd'); stats=self.store.stats(self.cfg['operator'],self.cfg['mode'],day[:7]); count=stats['days'].get(day,0)
        self.day_details.setText(f'{day} · 合格 {count} 个 · '+('今日目标已达成，记得留下你的感想。' if count>=self.cfg['daily_goal'] else f'距离目标还差 {self.cfg["daily_goal"]-count} 个，按自己的节奏继续。'))
    def refresh_analytics(self,*args):
        month=self.analytics_month.currentText()
        if not month: return
        stats=self.store.stats(self.cfg['operator'],self.cfg['mode'],month)
        self.statline.setText(f'{month}    {stats["total"]} 次观看     {stats["qualified"]} 次合格     {stats["reflections"]} 篇感想')
        self.chart.days=stats['days']; self.chart.month=month; self.chart.update()
        rows=[r for r in self.store.records() if r['operator']==self.cfg['operator'] and r['mode']==self.cfg['mode'] and r['timestamp'].startswith(month)]
        self.chart.series={}
        for r in rows:
            days=self.chart.series.setdefault(r['category'],{}); day=r['timestamp'][:10]; days[day]=days.get(day,0)+(r['ratio']>=.95)
        self.chart.update()
        for widget in (self.category_chart,self.trend_chart): widget.rows=rows; widget.month=month; widget.update()
        self.summary.setText('统计包含本地已保存、尚待同步的登记。无登记日期不计算达标率。')
    def apply_theme(self):
        theme=self.cfg.get('theme','sage')
        if theme=='light': theme='sage'
        dark=theme=='dark'
        palettes={
            'sage':dict(bg='#f1f5f1',panel='#ffffff',fg='#24352d',border='#d5e0d8',accent='#397c5c',selected='#dcece1',muted='#71877a'),
            'rose':dict(bg='#fbf1f1',panel='#ffffff',fg='#432e32',border='#ead4d7',accent='#bd5967',selected='#f5dfe2',muted='#94757a'),
            'dark':dict(bg='#141518',panel='#202226',fg='#eeeeef',border='#34373d',accent='#65b885',selected='#315c48',muted='#98a0aa')}
        p=palettes.get(theme,palettes['sage']); bg,panel,fg,border,accent,selected,muted=(p[k] for k in ('bg','panel','fg','border','accent','selected','muted'))
        self.setStyleSheet(f'''QWidget {{background:{bg};color:{fg};font-family:"Microsoft YaHei UI";font-size:12px;}}
        QFrame#card {{background:{panel};border:1px solid {border};border-radius:12px;}}
        QFrame#card QLabel {{background:transparent;}}
        QLabel#heading {{font-size:24px;font-weight:700;}} QLabel#welcome {{font-size:15px;padding:4px 0 8px;}}
        QLabel#eyebrow {{font-size:11px;color:{muted};}} QLabel#statline {{font-size:18px;font-weight:600;}}
        QLineEdit,QTextEdit,QComboBox,QSpinBox,QTableWidget {{background:{panel};border:1px solid {border};border-radius:6px;padding:7px;}}
        QPushButton {{background:{panel};border:1px solid {border};border-radius:7px;padding:8px 12px;}}
        QPushButton:hover {{border-color:{accent};}} QPushButton#primary {{background:{accent};color:white;border:0;font-weight:600;}}
        QPushButton:checked {{background:{selected};color:{fg};border-color:{accent};}} QToolTip {{background:{panel};color:{fg};border:1px solid {border};padding:12px;}}
        QProgressBar {{border:0;background:{border};border-radius:4px;text-align:center;min-height:8px;}}
        QProgressBar::chunk {{background:{accent};border-radius:4px;}}
        QCalendarWidget QToolButton {{color:{fg};background:{panel};border:0;padding:4px;}}
        QCalendarWidget QWidget#qt_calendar_navigationbar {{background:{panel};}}
        QCalendarWidget QAbstractItemView {{background:{panel};selection-background-color:transparent;}}
        QSplitter::handle {{background:{border};width:1px;}} QScrollArea {{border:0;}}
        ''')
        header=QTextCharFormat(); header.setBackground(QColor(panel)); header.setForeground(QColor(fg)); self.calendar.setHeaderTextFormat(header)
    def open_youtube(self):
        self.save_draft()
        self.tracker=Tracker(); self.submit.setEnabled(False); self.browser.setUrl(QUrl('https://www.youtube.com/?hl=zh-CN'))
    def toggle_theme(self):
        order=['sage','rose','dark']; self.cfg['theme']=order[(order.index(self.cfg['theme'])+1)%len(order)] if self.cfg['theme'] in order else 'sage'; self.store.save_config(self.cfg); self.apply_theme()
        self.settings_page.fields['theme'].setCurrentIndex(max(0,self.settings_page.fields['theme'].findData(self.cfg['theme'])))
    def loaded(self,ok):
        if self.browser.url().scheme() not in ('http','https'):
            if self.tracker.video=='local-demo': self.browser.page().allow_local_demo=False
            self.browser_status.setText('本地演示 · 点击顶部“打开 YouTube”进入真实网页'); return
        self.browser_status.setText('YouTube 已加载 · 在页面中搜索或打开视频' if ok else '网页加载失败，请检查网络后点击 ↻ 重试')
    def navigate(self):
        url=QUrl.fromUserInput(self.address.text())
        if url.scheme() in ('http','https'): self.browser.setUrl(url)
    def demo(self):
        self.browser.page().allow_local_demo=True
        self.browser.setHtml('<html><body style="background:#132338;color:#e1ecef;font:22px sans-serif;padding:70px"><h1>静心 · 本地演示</h1><p>先验证登记与成长数据，再连接你的表格。</p><p>示例视频为 100 秒，已观看 95 秒。</p><p>点击右侧登记按钮即可查看本地模拟同步结果。</p></body></html>')
        self.tracker=Tracker(); self.tracker.video='local-demo'; self.tracker.title='每日灵修 · 本地示例'; self.tracker.duration=100; self.tracker.intervals=[(0,95)]; self.show_tracking()
    def poll(self):
        if self.tracker.video=='local-demo' and self.browser.url().scheme() not in ('http','https'): return
        if not is_youtube_url(self.browser.url().toString()): self.submit.setEnabled(False); return
        self.browser.page().runJavaScript(self.probe,self.receive)
    def receive(self,result):
        try:
            data=json.loads(result) if result else None
            if not is_youtube_url(self.browser.url().toString()): self.submit.setEnabled(False); return
            data=validate_sample(data)
            if data and data['id']!=self.tracker.video:
                self.save_draft(); self.restore_draft(data['id'])
            if data and self.resume_position is not None:
                position=self.resume_position
                if data['duration']>0:
                    self.resume_position=None
                    self.browser.page().runJavaScript(seek_video_script(position))
                return
            self.tracker.sample(data)
            if data: self.show_tracking()
            if data and self.cfg.get('watch_download'):
                self.download_dialog.queue_current('https://www.youtube.com/watch?v='+data['id'])
            elif self.tracker.video!='local-demo': self.submit.setEnabled(False); self.update_avatar_status()
        except (ValueError,TypeError,KeyError): self.submit.setEnabled(False)
    def show_tracking(self):
        t=self.tracker; ratio=t.watched/t.duration if t.duration else 0
        self.title.setText(t.title); self.progress.setValue(int(ratio*100)); n=sum(r['url'].endswith(t.video) for r in self.store.records())
        self.metrics.setText(f'观看 {t.watched:.1f} / {t.duration:.1f} 秒 · {ratio:.1%}\n已登记 {n} 次 · 合格门槛 95%'); self.submit.setEnabled(t.duration>0)
        self.submit.setEnabled(t.duration>0 and not t.registered)
        self.update_avatar_status()
        if t.can_auto_register(self.cfg['operator'],self.category.currentText()): self.register(automatic=True)
        elif ratio>=.95 and not t.registered and t.video!='local-demo': self.status.setText('已达到 95%，填写登记人和分类后将自动登记。')
    def new_round(self): self.tracker.reset(); self.save_draft(); self.show_tracking(); self.status.setText('已开始新一轮，请从视频开头播放。')
    def settings(self):
        self.select_page(3)
    def save_mood(self,value):
        self.cfg['mood']=value; self.store.save_config(self.cfg)
        self.settings_page.fields['mood'].setText(value); self.refresh()
    def register(self,checked=False,automatic=False):
        t=self.tracker
        if t.registered: return
        if t.video=='local-demo' and self.cfg['mode']!='local': QMessageBox.warning(self,'演示数据','请先在设置中切换为 local 模式。'); return
        try:
            self.store.add(dict(session_id=t.round_id,operator=self.cfg['operator'],title=t.title,url='https://www.youtube.com/watch?v='+t.video,duration=t.duration,watched=t.watched,category=self.category.currentText().strip(),reflection=self.reflection.toPlainText().strip()),self.cfg)
        except ValueError as e: QMessageBox.warning(self,'无法登记',str(e)); return
        t.registered=True
        self.save_draft()
        self.reflection.clear(); self.refresh(); self.submit.setEnabled(False); self.status.setText(('达到 95%，已自动登记。' if automatic else '已登记。')+'本轮不会重复提交；再次观看请点击“开始新一轮观看”。'); self.sync()
    def sync(self):
        if self.worker and self.worker.isRunning(): return
        self.worker=Worker(self.store.root); self.worker.result.connect(self.synced); self.worker.start()
    def synced(self,result):
        ok,value=result
        if ok:
            done,errors=value; self.status.setText(f'本轮同步 {done} 条。'+ ('待重试：'+errors[0] if errors else '同步完成。'))
        else: self.status.setText(str(value))
        self.refresh()
    def categories(self):
        if self.cfg['mode']=='local': self.status.setText('本地模式使用本地历史分类，也可直接输入分类。'); return
        if getattr(self,'oauth_worker',None) and self.oauth_worker.isRunning():
            self.status.setText('Google 授权仍在收尾，请等应用提示“已连接 Google 账号”后再读取分类。'); return
        if self.worker and self.worker.isRunning(): return
        self.worker=Worker(self.store.root,self.cfg.copy()); self.worker.result.connect(self.got_categories); self.worker.start()
    def got_categories(self,result):
        ok,value=result
        if ok: self.cfg['categories']=value; self.store.save_config(self.cfg); self.refresh(); self.status.setText('分类已刷新。')
        else: self.status.setText('分类读取失败：'+str(value))
    def refresh(self,*args):
        self.banner.setText(('本地模拟 · 不写入 Google Sheets' if self.cfg['mode']=='local' else '在线同步 · 将写入已配置的 Google Sheets')+'    登记人：'+(self.cfg['operator'] or '请在设置中填写'))
        selected=self.category.currentText(); self.category.clear(); self.category.addItems(sorted(set(self.cfg['categories']+self.store.categories()))); self.category.setCurrentText(selected)
        month=f'{self.calendar.yearShown():04}-{self.calendar.monthShown():02}'; stats=self.store.stats(self.cfg['operator'],self.cfg['mode'],month)
        stage='幼苗' if stats['level']==1 else '小树' if stats['level']<4 else '枝繁叶茂'
        self.tree.setText(f"{stage} · 成长等级 {stats['level']}  ·  {'健康成长' if stats['health']>=60 else '需要你的照料'}\n健康值 {stats['health']} / 100")
        self.welcome.setText(f"欢迎回来，{self.cfg['operator'] or '朋友'}  ·  {month}")
        self.plant.level=stats['level']; self.plant.health=stats['health']; self.plant.update(); self.healthbar.setValue(stats['health'])
        self.statline.setText(f"{stats['total']} 次观看     {stats['qualified']} 次合格     {stats['reflections']} 篇感想")
        today=date.today(); daily=self.store.stats(self.cfg['operator'],self.cfg['mode'])['days'].get(today.isoformat(),0)
        self.dailybar.setValue(min(100,round(daily/self.cfg['daily_goal']*100))); self.dailybar.setFormat(f'今日完成 {daily} / {self.cfg["daily_goal"]}')
        self.calendar.days=stats['days']; self.calendar.goal=self.cfg['daily_goal']; self.calendar.updateCells()
        self.summary.setText(f"本月登记 {stats['total']} · 合格 {stats['qualified']} · 观后感 {stats['reflections']}\n今日目标还差 {max(0,self.cfg['daily_goal']-daily)} 个；所选月额度剩余 {max(0,self.cfg['monthly_goal']-stats['qualified'])} 个。")
        for d in range(1,calendar.monthrange(self.calendar.yearShown(),self.calendar.monthShown())[1]+1):
            q=QDate(self.calendar.yearShown(),self.calendar.monthShown(),d); fmt=QTextCharFormat()
            if q<=QDate.currentDate(): fmt.setBackground(QColor('#277c60' if stats['days'].get(q.toString('yyyy-MM-dd'),0)>=self.cfg['daily_goal'] else '#984f59')); fmt.setForeground(QColor('white'))
            self.calendar.setDateTextFormat(q,fmt)
        self.chart.days=stats['days']; self.chart.month=month; self.chart.update()
        rows=self.store.records(); self.history.setRowCount(len(rows))
        for i,r in enumerate(rows):
            for j,value in enumerate([r['timestamp'],r['title'],f"{r['ratio']:.1%}",r['mode']+'/'+r['status'],r['error']]): self.history.setItem(i,j,QTableWidgetItem(value))
        self.history.resizeColumnsToContents()
        pixmap=QPixmap(self.cfg['avatar_path']) if self.cfg['avatar_path'] else QPixmap()
        self.avatar.setIcon(QIcon(avatar_image(pixmap,128,circular=True))); self.avatar.setIconSize(QSize(34,34)); self.avatar.setText('' if not pixmap.isNull() else self.cfg['operator'][:1] or '我')
        self.avatar.setStyleSheet('padding:3px;border-radius:21px;')
        self.update_avatar_status()
        current=self.analytics_month.currentText(); months=sorted({date.today().strftime('%Y-%m')}|{r['timestamp'][:7] for r in rows},reverse=True)
        self.analytics_month.blockSignals(True); self.analytics_month.clear(); self.analytics_month.addItems(months); self.analytics_month.setCurrentText(current if current in months else months[0]); self.analytics_month.blockSignals(False)
        self.refresh_analytics(); self.selected_day()
    def update_avatar_status(self):
        import html
        t=self.tracker; stats=self.store.stats(self.cfg['operator'],self.cfg['mode']); daily=stats['days'].get(date.today().isoformat(),0)
        ratio=t.watched/t.duration if t.duration else 0
        state='本轮已登记' if t.registered else '正在播放' if t.last and t.last.get('playing') else '暂停或等待视频'
        stage='幼苗' if stats['level']==1 else '小树' if stats['level']<4 else '枝繁叶茂'
        self.avatar.setToolTip(f"<b>{html.escape(self.cfg['operator'] or '未设置登记人')}</b><br>当前视频：{html.escape(t.title or '尚未播放')}<br>观看进度：{ratio:.1%}（{t.watched:.0f} / {t.duration:.0f} 秒）<br>播放状态：{state}<br>今日合格：{daily} / {self.cfg['daily_goal']}<br>心情：{html.escape(self.cfg['mood'])}<br>小树：{stage} · Lv.{stats['level']}<br>健康值：{stats['health']} / 100<br>每完成 5 次合格观看升一级")
    def closeEvent(self,event):
        if self.download_dialog.process.state()!=self.download_dialog.process.ProcessState.NotRunning:
            self.download_dialog.stop()
            self.download_dialog.process.waitForFinished(1500)
        if self.worker and self.worker.isRunning(): self.status.setText('正在完成同步，请稍后关闭。'); event.ignore(); return
        self.save_draft(); self.autosave.stop(); self.draft_timer.stop()
        self.timer.stop(); self.retry.stop(); self.screenshot_timer.stop(); self.browser.setPage(QWebEnginePage(self.browser)); self.store.db.close(); event.accept()

