import json
from .core import HEADERS, locate, log_values
from .security import safe_error

class LocalSheets:
    def __init__(self, store): self.store=store
    def sync(self,r,cfg):
        db=self.store.db
        with db:
            db.execute('INSERT OR IGNORE INTO local_log VALUES(?,?)',(r['id'],json.dumps(r,ensure_ascii=False)))
            if r['ratio']<.95 or db.execute('SELECT 1 FROM local_applied WHERE id=?',(r['id'],)).fetchone(): return
            key=json.dumps([r['operator'],r['timestamp'][:10],r['category']],ensure_ascii=False)
            old=db.execute('SELECT count,reflection FROM local_summary WHERE key=?',(key,)).fetchone()
            note=f"• 《{r['title']}》: {r['reflection']}" if r['reflection'] else ''
            text='\n'.join(x for x in [old['reflection'] if old else '',note] if x)
            db.execute('INSERT OR REPLACE INTO local_summary VALUES(?,?,?)',(key,(old['count'] if old else 0)+1,text))
            db.execute('INSERT INTO local_applied VALUES(?)',(r['id'],))

def insert_latest_log_row(worksheet, headers, values, record_id, header_row=1):
    """Insert new records directly below the header and remain idempotent on retries."""
    id_column=headers.index('记录ID')+1
    if record_id in worksheet.col_values(id_column): return False
    worksheet.insert_row(values,index=header_row+1,value_input_option='RAW',inherit_from_before=False)
    return True

class GoogleSheets:
    def __init__(self,cfg):
        import gspread
        from .oauth import load_credentials,oauth_client_id
        credentials=load_credentials(oauth_client_id(cfg['oauth_client_file']))
        if credentials is None: raise ValueError('请先在设置中连接 Google 账号')
        self.client=gspread.authorize(credentials)
        self.client.set_timeout(25)
    def sheet(self,key,title): return self.client.open_by_key(key).worksheet(title)
    def categories(self,cfg):
        log=self.sheet(cfg['log_id'],cfg['log_sheet'])
        headers=log.row_values(cfg['log_header_row'])
        values=log.col_values(headers.index('分类')+1)[cfg['log_header_row']:] if '分类' in headers else []
        if cfg['category_sheet']:
            values+=self.sheet(cfg['log_id'],cfg['category_sheet']).col_values(cfg['category_col'])[1:]
        return sorted({str(x).strip() for x in values if str(x).strip()})
    def sync(self,r,cfg):
        from gspread.utils import rowcol_to_a1
        log=self.sheet(cfg['log_id'],cfg['log_sheet']); header=log.row_values(cfg['log_header_row'])
        # Append missing PRD fields to the header, preserving the six-column example.
        missing=[h for h in HEADERS if h not in header]
        if missing:
            end=len(header)+len(missing)
            if end>log.col_count: log.add_cols(end-log.col_count)
            log.update(range_name=f"{rowcol_to_a1(cfg['log_header_row'],len(header)+1)}:{rowcol_to_a1(cfg['log_header_row'],end)}",values=[missing],raw=True)
            header+=missing
        if any(header.count(h)!=1 for h in HEADERS): raise ValueError('日志表存在重复字段名')
        mapping=dict(zip(HEADERS,log_values(r)))
        insert_latest_log_row(log,header,[mapping.get(h,'') for h in header],r['id'],cfg['log_header_row'])
        if r['ratio']<.95: return
        ws=self.sheet(cfg['summary_id'],cfg['summary_sheet'])
        values=ws.get_all_values(value_render_option='UNFORMATTED_VALUE')
        row,col,note_col=locate(values,cfg,r)
        a1=rowcol_to_a1(row,col)
        # Human-readable notes; retry IDs live in spreadsheet developer metadata.
        meta=ws.spreadsheet.fetch_sheet_metadata(params={'includeGridData':True,'ranges':f"'{ws.title.replace(chr(39),chr(39)*2)}'!{a1}"})
        cells=meta['sheets'][0].get('data',[{}])[0].get('rowData',[{}])[0].get('values',[{}])
        old_note=cells[0].get('note','') if cells else ''
        marker=f"[devotion:{r['id']}]"
        if marker in old_note or any(m.get('metadataKey')=='devotion_record' and m.get('metadataValue')==r['id'] for m in meta.get('developerMetadata',[])): return
        old=ws.acell(a1,value_render_option='FORMULA').value
        if str(old or '').startswith('='): raise ValueError(f'{a1} 是公式，拒绝覆盖')
        try: number=float(old or 0)
        except ValueError: raise ValueError(f'{a1} 不是数值')
        if number<0 or not number.is_integer(): raise ValueError('汇总计数必须为非负整数')
        def update(c,value,note=None):
            data={'userEnteredValue':value}
            if note is not None: data['note']=note
            return {'updateCells':{'range':{'sheetId':ws.id,'startRowIndex':row-1,'endRowIndex':row,'startColumnIndex':c-1,'endColumnIndex':c},'rows':[{'values':[data]}],'fields':'userEnteredValue'+(',note' if note is not None else '')}}
        title_note='\n'.join(x for x in [old_note,f"• 《{r['title']}》"] if x)
        requests=[update(col,{'numberValue':number+1},title_note)]
        if r['reflection']:
            before=ws.cell(row,note_col,value_render_option='FORMULA').value or ''
            if str(before).startswith('='): raise ValueError('认识栏是公式，拒绝覆盖')
            requests.append(update(note_col,{'stringValue':'\n'.join(x for x in [str(before),f"• 《{r['title']}》: {r['reflection']}"] if x)}))
        requests.append({'createDeveloperMetadata':{'developerMetadata':{
            'metadataKey':'devotion_record','metadataValue':r['id'],
            'location':{'spreadsheet':True},'visibility':'DOCUMENT'}}})
        ws.spreadsheet.batch_update({'requests':requests})

def sync_pending(store):
    errors=[]; done=0
    for item in store.db.execute("SELECT * FROM records WHERE status!='synced' ORDER BY rowid").fetchall():
        r=json.loads(item['payload']); cfg=json.loads(item['config'])
        try:
            backend=LocalSheets(store) if cfg['mode']=='local' else GoogleSheets(cfg)
            backend.sync(r,cfg)
            with store.db: store.db.execute("UPDATE records SET status='synced',error='' WHERE id=?",(r['id'],))
            done+=1
        except Exception as e:
            with store.db: store.db.execute("UPDATE records SET status='pending',error=? WHERE id=?",(safe_error(e),r['id']))
            errors.append(safe_error(e))
    return done,errors
