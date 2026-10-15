"""Read-only GitHub release checks. The user installs packages from the official release page."""
import json
import re
from urllib.request import Request, urlopen

VERSION = '0.2.1'
REPOSITORY = 'christiancagfr-alt/videodaka'
RELEASES_PAGE = f'https://github.com/{REPOSITORY}/releases/latest'
API_URL = f'https://api.github.com/repos/{REPOSITORY}/releases/latest'


def version_tuple(value):
    if not isinstance(value, str):
        return None
    match = re.fullmatch(r'v?(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:[-+][0-9A-Za-z.-]+)?', value.strip())
    return tuple(map(int, match.groups())) if match else None


def latest_release(timeout=5):
    request = Request(API_URL, headers={
        'Accept': 'application/vnd.github+json',
        'X-GitHub-Api-Version': '2022-11-28',
        'User-Agent': 'DevotionFlow-update-check',
    })
    with urlopen(request, timeout=timeout) as response:
        if response.status != 200:
            raise RuntimeError('GitHub 更新服务暂时不可用')
        data = json.loads(response.read(1024 * 1024 + 1))
    if not isinstance(data, dict) or data.get('draft') or data.get('prerelease'):
        return None
    tag = data.get('tag_name')
    remote = version_tuple(tag)
    current = version_tuple(VERSION)
    page = data.get('html_url')
    if not remote or not current or remote <= current:
        return None
    if page != RELEASES_PAGE and not (isinstance(page, str) and re.fullmatch(
            rf'https://github\.com/{re.escape(REPOSITORY)}/releases/tag/[A-Za-z0-9._+-]+', page)):
        raise RuntimeError('更新信息的来源地址无效')
    return {'version': tag, 'url': page, 'name': str(data.get('name') or tag)[:160]}
