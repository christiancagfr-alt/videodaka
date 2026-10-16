"""Small, built-in filter for common YouTube advertising endpoints."""
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
