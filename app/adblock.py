"""Local request filtering and safe loading of the bundled YouTube userscript.

Media requests are intentionally allowed because YouTube can serve both ads and
the requested video from the same Google Video CDN.
"""
import re
import sys
import hashlib
from pathlib import Path
from urllib.parse import urlsplit

# Curated hostname-level baseline for common ad networks, exchanges, and trackers.
# This is intentionally conservative: broad Google video/CDN hosts stay allowed.
AD_HOSTS={
    # Google / YouTube ad serving
    'doubleclick.net','googlesyndication.com','googleadservices.com',
    'adservice.google.com','ads.youtube.com','ads.google.com',
    'partnerad.l.google.com','s0.2mdn.net','2mdn.net',
    # Major ad exchanges and supply-side platforms
    'adnxs.com','appnexus.com','adsrvr.org','adform.net','adform.com',
    'pubmatic.com','openx.net','rubiconproject.com','casalemedia.com',
    'criteo.com','criteo.net','taboola.com','outbrain.com','smartadserver.com',
    'sharethrough.com','indexexchange.com','lijit.com',
    'contextweb.com','media.net','yieldmo.com','triplelift.com','bidr.io',
    'advertising.com','adtech.de','adition.com','adkernel.com','admanmedia.com',
    'admarvel.com','adroll.com','undertone.com','smaato.net','improvedigital.com',
    '33across.com','teads.tv','themediagrid.com','sonobi.com',
    'emxdgt.com','rhythmone.com','spotxchange.com','spotx.tv','sharethrough.com',
    'smartadserver.com','adyoulike.com','revcontent.com','mgid.com','dianomi.com',
    # Common ad / conversion measurement endpoints
    'quantserve.com','scorecardresearch.com','moatads.com','adsafeprotected.com',
    'doubleverify.com','integralads.com','imrworldwide.com','nielsen.com',
    'demdex.net','bluekai.com','krxd.net','rlcdn.com','tapad.com','eyeota.net',
    'exelator.com','agkn.com','adlooxtracking.com','serving-sys.com',
    'measurementapi.com','mathtag.com','mookie1.com','bidswitch.net','adalyser.com',
    # Frequently seen regional ad systems (including China)
    'tanx.com','alimama.com','cpro.baidu.com','pos.baidu.com','union.baidu.com',
    'hm.baidu.com','gdt.qq.com','l.qq.com','ad.qq.com','e.qq.com','ssp.qq.com',
    'p.tencentmind.com','adsame.com','miaozhen.com','ipinyou.com','admaster.com.cn',
    'adview.cn','adukwai.com','ads8.com','umeng.com',
    # Mobile app ad networks and attribution providers
    'applovin.com','unityads.unity3d.com','ironsrc.com','vungle.com',
    'chartboost.com','inmobi.com','adcolony.com','mintegral.com',
    'adjust.com','appsflyer.com','branch.io','kochava.com',
}

YOUTUBE_AD_PATHS=('/pagead/', '/api/stats/ads', '/get_midroll_info')
DOMAIN_LABEL=re.compile(r'^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$')

def normalize_ad_domains(domains):
    """Validate a bounded list of plain DNS names used only for request blocking."""
    if isinstance(domains,str): domains=domains.splitlines()
    if not isinstance(domains,(list,tuple,set)): raise ValueError('广告域名必须是一行一个域名。')
    if len(domains)>500: raise ValueError('本地广告域名最多保存 500 条。')
    normalized=[]
    for raw in domains:
        if not isinstance(raw,str): raise ValueError('广告域名格式无效。')
        value=raw.strip().lower().rstrip('.')
        if not value: continue
        if len(value)>253 or '://' in value or '/' in value or ':' in value or '*' in value:
            raise ValueError(f'“{raw}”不是有效的纯域名，请勿输入网址、路径或通配符。')
        try: value=value.encode('idna').decode('ascii')
        except UnicodeError as exc: raise ValueError(f'“{raw}”不是有效域名。') from exc
        labels=value.split('.')
        if len(labels)<2 or any(not DOMAIN_LABEL.fullmatch(label) for label in labels):
            raise ValueError(f'“{raw}”不是有效的域名。')
        if value not in normalized: normalized.append(value)
    return normalized

def should_block_ad_request(url,extra_domains=()):
    try:
        parsed=urlsplit(url)
        host=(parsed.hostname or '').lower().rstrip('.')
        try: custom=set(normalize_ad_domains(extra_domains))
        except ValueError: custom=set()
        domains=AD_HOSTS|custom
        if any(host==domain or host.endswith('.'+domain) for domain in domains): return True
        if host not in {'youtube.com','www.youtube.com','m.youtube.com'}: return False
        path=parsed.path.lower()
        if any(path.startswith(prefix) for prefix in YOUTUBE_AD_PATHS): return True
        # Do not cancel player metadata, telemetry, or googlevideo media
        # requests: they are also required for normal video playback.
        return False
    except (TypeError,ValueError):
        return False

def bundled_youtube_adblock_script():
    """Read the pinned, locally bundled userscript in source and PyInstaller builds."""
    base=Path(getattr(sys,'_MEIPASS',Path(__file__).resolve().parents[1]))
    path=base/'third_party'/'YoutubeAdblock'/'YoutubeAdblock.user.js'
    raw=path.read_bytes()
    expected='b44f5d737405bf104b9a7a48686f33c158f996b7fefc6bd454a32136fbada032'
    if hashlib.sha256(raw.replace(b'\r\n',b'\n')).hexdigest()!=expected:
        raise RuntimeError('内置 YoutubeAdblock 脚本完整性校验失败。')
    return raw.decode('utf-8')

def youtube_adblock_injection_source():
    """Adapt the upstream userscript to a document-start, same-origin Qt injection."""
    shim=r'''(() => {
 if (!['www.youtube.com','youtube.com','m.youtube.com','music.youtube.com','tv.youtube.com','www.youtube-nocookie.com','youtubekids.com','www.youtubekids.com'].includes(location.hostname)) return;
 const key = name => '__devotionflow_yab_v082_' + String(name);
 window.GM_getValue = (name, fallback) => {
   try { const value = localStorage.getItem(key(name)); return value === null ? fallback : JSON.parse(value); }
   catch (_) { return fallback; }
 };
 window.GM_setValue = (name, value) => {
   try { localStorage.setItem(key(name), JSON.stringify(value)); } catch (_) {}
 };
 // Cross-origin GM_xmlhttpRequest is intentionally unavailable: the bundled
 // engine stays on its signed built-in rules and never fetches remote scripts.
 window.GM_xmlhttpRequest = undefined;
 window.GM_registerMenuCommand = undefined;
 window.GM_unregisterMenuCommand = undefined;
})();
'''
    return shim+'\n'+bundled_youtube_adblock_script()

try:
    from PySide6.QtWebEngineCore import QWebEngineUrlRequestInterceptor
except ImportError:  # Allows pure rule tests when Qt is not installed.
    QWebEngineUrlRequestInterceptor=object

class YouTubeAdBlocker(QWebEngineUrlRequestInterceptor):
    def __init__(self,parent=None,extra_domains=()):
        super().__init__(parent)
        self.enabled=True
        self.extra_domains=normalize_ad_domains(extra_domains)

    def set_domains(self,domains):
        self.extra_domains=normalize_ad_domains(domains)

    def interceptRequest(self,info):
        if self.enabled and should_block_ad_request(info.requestUrl().toString(),self.extra_domains):
            info.block(True)
