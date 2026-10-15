"""Validation for data crossing browser, credential and process boundaries."""
import json
import math
import os
from pathlib import Path
import re
from urllib.parse import urlsplit

YOUTUBE_HOSTS={'youtube.com','www.youtube.com','m.youtube.com','music.youtube.com'}
TOKEN_URIS={'https://oauth2.googleapis.com/token','https://accounts.google.com/o/oauth2/token'}

def is_youtube_url(url):
    try:
        parsed=urlsplit(url)
        return parsed.scheme=='https' and parsed.hostname in YOUTUBE_HOSTS and parsed.port in (None,443) and not parsed.username and not parsed.password
    except ValueError: return False

def valid_video_id(value):
    return isinstance(value,str) and re.fullmatch(r'[A-Za-z0-9_-]{1,128}',value) is not None

def validate_sample(value):
    if not isinstance(value,dict) or not valid_video_id(value.get('id')): return None
    if not isinstance(value.get('title',''),str) or len(value.get('title',''))>10000: return None
    if not isinstance(value.get('playing'),bool): return None
    for key in ('duration','position','clock','rate'):
        number=value.get(key,1 if key=='rate' else None)
        if isinstance(number,bool) or not isinstance(number,(float,int)) or not math.isfinite(number) or number<0: return None
    if value['duration']>31_536_000 or value['position']>31_536_000: return None
    return value

def load_service_account(path):
    selected=Path(path).expanduser()
    if selected.stat().st_size>128*1024: raise ValueError('服务账号文件过大')
    data=json.loads(selected.read_text('utf-8-sig'))
    if not isinstance(data,dict) or data.get('type')!='service_account': raise ValueError('请选择服务账号 JSON 文件')
    if data.get('token_uri') not in TOKEN_URIS: raise ValueError('服务账号授权地址必须是 Google 官方 HTTPS 地址')
    if not all(isinstance(data.get(k),str) and data[k].strip() for k in ('client_email','private_key','project_id')):
        raise ValueError('服务账号文件缺少必要字段')
    if not data['client_email'].endswith('.iam.gserviceaccount.com'): raise ValueError('服务账号邮箱格式无效')
    return data

def safe_error(error):
    text=str(error)
    text=re.sub(r'-----BEGIN [^-]*PRIVATE KEY-----.*?-----END [^-]*PRIVATE KEY-----','[私钥已隐藏]',text,flags=re.S)
    text=re.sub(r'(?i)(Bearer\s+)[A-Za-z0-9._~+/-]+=*',r'\1[已隐藏]',text)
    text=re.sub(r'(?i)((?:access_token|refresh_token|client_secret|api_key|token|key|sig|signature)[\"\x27]?\s*[:=]\s*[\"\x27]?)[^\s&\"\x27,}]+',r'\1[已隐藏]',text)
    return text[:1800]

def private_directory(path):
    path=Path(path); path.mkdir(parents=True,exist_ok=True)
    if os.name!='nt': path.chmod(0o700)
    return path
