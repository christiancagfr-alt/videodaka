"""Small, built-in filter for common YouTube advertising endpoints."""
import json
from pathlib import Path
from urllib.parse import urlsplit

AD_HOSTS={
    'doubleclick.net','googlesyndication.com','googleadservices.com',
    'adservice.google.com','ads.youtube.com',
}
YOUTUBE_AD_PATHS=('/pagead/','/api/stats/ads','/get_midroll_info')

def should_block_ad_request(url):
    try:
        parsed=urlsplit(url)
        host=(parsed.hostname or '').lower().rstrip('.')
        if any(host==domain or host.endswith('.'+domain) for domain in AD_HOSTS): return True
        return host in {'youtube.com','www.youtube.com','m.youtube.com'} and any(
            parsed.path.startswith(path) for path in YOUTUBE_AD_PATHS)
    except (TypeError,ValueError):
        return False

def validate_extension_directory(path):
    """Validate an explicitly selected unpacked MV3 extension before handing it to Qt."""
    directory=Path(path).resolve(strict=True)
    manifest_path=directory/'manifest.json'
    if not directory.is_dir() or not manifest_path.is_file():
        raise ValueError('文件夹中没有有效的 manifest.json。')
    if manifest_path.stat().st_size>1024*1024:
        raise ValueError('扩展 manifest.json 超过 1 MB。')
    try:
        manifest=json.loads(manifest_path.read_text(encoding='utf-8'))
    except (UnicodeError,json.JSONDecodeError) as exc:
        raise ValueError('扩展 manifest.json 不是有效的 UTF-8 JSON。') from exc
    if (not isinstance(manifest,dict) or manifest.get('manifest_version')!=3
            or not isinstance(manifest.get('name'),str) or not manifest['name'].strip()):
        raise ValueError('仅支持包含有效名称的 Manifest V3 扩展。')
    return directory,manifest

try:
    from PySide6.QtWebEngineCore import QWebEngineUrlRequestInterceptor
except ImportError:  # Allows pure rule tests when Qt is not installed.
    QWebEngineUrlRequestInterceptor=object

class YouTubeAdBlocker(QWebEngineUrlRequestInterceptor):
    def __init__(self,parent=None):
        super().__init__(parent)
        self.enabled=True

    def interceptRequest(self,info):
        if self.enabled and should_block_ad_request(info.requestUrl().toString()):
            info.block(True)
