import json
import math
import sqlite3
import uuid
from datetime import datetime, date, timedelta
from pathlib import Path
from .security import private_directory,valid_video_id

DEFAULTS = dict(operator='', mode='local', credentials='', log_id='', log_sheet='日志',
                summary_id='', summary_sheet='10月', date_row=1, category_row=2,
                name_col=1, first_person_row=5, reflection_header='认识', daily_goal=2,
                monthly_goal=50, theme='sage', avatar='🌱', avatar_path='', sidebar_collapsed=False, mood='平静', categories=[],
                download_dir='', download_quality='1080', ffmpeg_path='', watch_download=False, auto_install_ffmpeg=True,
                screenshot_dir='', screenshot_interval=0,
                log_header_row=1, category_sheet='分类', category_col=1, oauth_client_file='',oauth_connected=False,oauth_email='')
HEADERS = ['登记时间','登记人','视频标题','视频链接','视频总时长','观看时长','分类','个人观后感','完播率','记录ID']

class Store:
    def __init__(self, root):
        self.root = private_directory(root)
        self.db = sqlite3.connect(self.root / 'records.sqlite', timeout=30)
        self.db.row_factory = sqlite3.Row
        self.db.executescript('''CREATE TABLE IF NOT EXISTS records (
          id TEXT PRIMARY KEY, payload TEXT NOT NULL, config TEXT NOT NULL,
          status TEXT NOT NULL DEFAULT 'pending', error TEXT NOT NULL DEFAULT '');
          CREATE TABLE IF NOT EXISTS local_log(id TEXT PRIMARY KEY, payload TEXT);
          CREATE TABLE IF NOT EXISTS local_summary(key TEXT PRIMARY KEY, count INTEGER, reflection TEXT);
          CREATE TABLE IF NOT EXISTS local_applied(id TEXT PRIMARY KEY);''')
        self.db.execute('CREATE TABLE IF NOT EXISTS state(key TEXT PRIMARY KEY,value TEXT NOT NULL)')
    def save_state(self,key,value):
        with self.db: self.db.execute('INSERT OR REPLACE INTO state VALUES(?,?)',(key,json.dumps(value,ensure_ascii=False)))
    def load_state(self,key,default=None):
        row=self.db.execute('SELECT value FROM state WHERE key=?',(key,)).fetchone()
        return json.loads(row[0]) if row else default
    def has_record(self,record_id):
        return bool(self.db.execute('SELECT 1 FROM records WHERE id=?',(record_id,)).fetchone())
    def config(self):
        p = self.root / 'settings.json'
        return DEFAULTS | (json.loads(p.read_text('utf-8')) if p.exists() else {})
    def save_config(self, cfg):
        p = self.root / 'settings.tmp'
        p.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), 'utf-8')
        p.replace(self.root / 'settings.json')
    def add(self, record, cfg):
        if not record['operator'].strip() or not record['category'].strip():
            raise ValueError('请填写登记人和分类')
        if not all(isinstance(record[k],(int,float)) and math.isfinite(record[k]) for k in ('duration','watched')) or record['duration'] <= 0 or not 0 <= record['watched'] <= record['duration']:
            raise ValueError('视频时长或观看时长无效')
        record = dict(record, id=record.get('session_id') or str(uuid.uuid4()), timestamp=datetime.now().astimezone().isoformat(timespec='seconds'))
        record['ratio'] = record['watched'] / record['duration']
        with self.db:
            self.db.execute('INSERT OR IGNORE INTO records(id,payload,config) VALUES(?,?,?)',
                            (record['id'], json.dumps(record,ensure_ascii=False), json.dumps(cfg,ensure_ascii=False)))
        return record
    def records(self):
        return [dict(json.loads(r['payload']), status=r['status'], error=r['error'], mode=json.loads(r['config'])['mode']) for r in self.db.execute('SELECT * FROM records ORDER BY rowid DESC')]
    def categories(self):
        return sorted({r['category'] for r in self.records()})
    def stats(self, operator, mode, month=None):
        today = date.today(); month = month or today.strftime('%Y-%m')
        rows = [r for r in self.records() if r['operator']==operator and r['mode']==mode]
        monthly = [r for r in rows if r['timestamp'].startswith(month)]
        days = {}
        for r in monthly:
            key = r['timestamp'][:10]
            days[key] = days.get(key,0) + (r['ratio'] >= .95)
        eligible = [r for r in rows if r['ratio'] >= .95]
        gap = (today-date.fromisoformat(max(r['timestamp'][:10] for r in eligible))).days if eligible else 0
        return dict(total=len(monthly), qualified=sum(r['ratio']>=.95 for r in monthly),
                    reflections=sum(bool(r['reflection'].strip()) for r in monthly), days=days,
                    level=1+len(eligible)//5, health=max(0,100-max(0,gap-1)*15))

class Tracker:
    """Unique played intervals per viewing session; seeks and repeated segments do not inflate coverage."""
    def __init__(self):
        self.video=''; self.title=''; self.duration=0.; self.intervals=[]; self.last=None; self.registered=False; self.round_id=str(uuid.uuid4()); self.position=0
    def reset(self):
        self.intervals=[]; self.last=None; self.registered=False; self.round_id=str(uuid.uuid4()); self.position=0
    def snapshot(self):
        return dict(video=self.video,title=self.title,duration=self.duration,intervals=self.intervals,registered=self.registered,round_id=self.round_id,position=self.position)
    def restore(self,value):
        if not isinstance(value,dict) or not valid_video_id(value.get('video')): raise ValueError('保存的视频记录无效')
        duration=value.get('duration',0); position=value.get('position',0)
        if not all(isinstance(v,(float,int)) and math.isfinite(v) and 0<=v<=31_536_000 for v in (duration,position)):
            raise ValueError('保存的播放位置无效')
        spans=value.get('intervals',[])
        if not isinstance(spans,list) or len(spans)>100000: raise ValueError('观看记录过大或无效')
        for span in spans:
            if not isinstance(span,(list,tuple)) or len(span)!=2 or not all(isinstance(v,(float,int)) and math.isfinite(v) for v in span) or not 0<=span[0]<=span[1]<=duration:
                raise ValueError('保存的观看区间无效')
        for key in ('video','title','duration','intervals','registered','round_id','position'):
            if key in value: setattr(self,key,value[key])
        # JSON restores interval pairs as lists; normalize them so new tuple spans
        # can be sorted and merged safely after playback resumes.
        self.intervals=[(float(start),float(end)) for start,end in spans]
        self.last=None
    def can_auto_register(self,operator,category):
        return bool(not self.registered and self.video and self.video!='local-demo' and self.duration>0 and self.watched/self.duration>=.95 and operator.strip() and category.strip())
    @property
    def watched(self):
        return sum(b-a for a,b in self.intervals)
    def sample(self, s):
        if not s or not s.get('id'):
            self.last=None; return
        if s['id'] != self.video:
            self.video=s['id']; self.reset()
        self.title=s.get('title',''); self.duration=float(s.get('duration',0))
        if not math.isfinite(self.duration): self.duration=0
        p=float(s['position']); now=float(s['clock'])
        if self.last and self.duration > 0:
            old=self.last; dt=(now-old['clock'])/1000; delta=p-old['position']
            if old['playing'] and s['playing'] and not s.get('seeking') and not old.get('seeking') and 0<dt<=2 and 0<delta<=dt*old.get('rate',1)+.35:
                spans=sorted(self.intervals+[(max(0,old['position']),min(p,self.duration))]); merged=[]
                for a,b in spans:
                    if b<=a: continue
                    if merged and a<=merged[-1][1]: merged[-1]=(merged[-1][0],max(b,merged[-1][1]))
                    else: merged.append((a,b))
                self.intervals=merged
        self.last=s
        self.position=p

def day_value(v):
    if isinstance(v, (int,float)): return (datetime(1899,12,30)+timedelta(days=v)).date().isoformat()
    if isinstance(v,(datetime,date)): return v.date().isoformat() if isinstance(v,datetime) else v.isoformat()
    s=str(v).strip()
    for fmt in ('%Y-%m-%d','%Y/%m/%d','%m/%d/%Y','%Y年%m月%d日'):
        try: return datetime.strptime(s,fmt).date().isoformat()
        except ValueError: pass
    return None

def locate(values,cfg,record):
    def cell(r,c): return values[r-1][c-1] if r<=len(values) and c<=len(values[r-1]) else ''
    rows=[r for r in range(cfg['first_person_row'],len(values)+1) if str(cell(r,cfg['name_col'])).strip()==record['operator'].strip()]
    if len(rows)!=1: raise ValueError('汇总表姓名缺失或重复，请检查姓名列与起始行')
    current=None; counts=[]; notes=[]
    width=max(map(len,values),default=0)
    for c in range(1,width+1):
        raw=cell(cfg['date_row'],c)
        if raw!='' and raw is not None: current=day_value(raw)
        if current==record['timestamp'][:10]:
            label=str(cell(cfg['category_row'],c)).strip()
            if label==record['category']: counts.append(c)
            if label==cfg['reflection_header']: notes.append(c)
    if len(counts)!=1 or (record['reflection'] and len(notes)!=1):
        raise ValueError('日期/分类/认识栏匹配不唯一；请检查完整日期、表头行和分类')
    return rows[0],counts[0],notes[0] if notes else None

def log_values(r):
    return [r[k] for k in ('timestamp','operator','title','url','duration','watched','category','reflection','ratio','id')]
