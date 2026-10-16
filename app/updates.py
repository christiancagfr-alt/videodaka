"""Check, download, and verify installers from the official GitHub release."""
import hashlib
import json
import os
import platform
import re
import sys
import tempfile
from urllib.request import Request, urlopen

VERSION = '0.2.7'
REPOSITORY = 'christiancagfr-alt/videodaka'
RELEASES_PAGE = f'https://github.com/{REPOSITORY}/releases/latest'
API_URL = f'https://api.github.com/repos/{REPOSITORY}/releases/latest'
MAX_INSTALLER_BYTES = 1_500_000_000


def version_tuple(value):
    if not isinstance(value, str):
        return None
    match = re.fullmatch(r'v?(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:[-+][0-9A-Za-z.-]+)?', value.strip())
    return tuple(map(int, match.groups())) if match else None


def current_asset_name(version, system=None, machine=None):
    system = system or sys.platform
    machine = (machine or platform.machine()).lower()
    if system == 'win32' and machine in ('amd64', 'x86_64', 'x64'):
        return f'DevotionFlow-{version}-windows-x64-setup.exe'
    if system == 'darwin' and machine in ('arm64', 'aarch64'):
        return f'DevotionFlow-{version}-macos-arm64.dmg'
    if system == 'darwin' and machine in ('amd64', 'x86_64', 'x64'):
        return f'DevotionFlow-{version}-macos-x64.dmg'
    return None


def latest_release(timeout=5, system=None, machine=None):
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
    asset_name = current_asset_name(tag.lstrip('v'), system, machine)
    if not asset_name:
        raise RuntimeError('当前系统暂不支持应用内更新')
    assets = data.get('assets')
    asset = next((item for item in assets if isinstance(item, dict) and item.get('name') == asset_name), None) if isinstance(assets, list) else None
    if not asset:
        raise RuntimeError('新版发布包尚未就绪，请稍后重试')
    download_url = asset.get('browser_download_url')
    expected_url = f'https://github.com/{REPOSITORY}/releases/download/{tag}/{asset_name}'
    digest = asset.get('digest')
    if download_url != expected_url or not isinstance(digest, str) or not re.fullmatch(r'sha256:[0-9a-fA-F]{64}', digest):
        raise RuntimeError('更新安装包地址或校验信息无效')
    size = asset.get('size')
    if not isinstance(size, int) or size <= 0 or size > MAX_INSTALLER_BYTES:
        raise RuntimeError('更新安装包大小无效')
    return {'version': tag, 'url': page, 'name': str(data.get('name') or tag)[:160],
            'asset': {'name': asset_name, 'url': download_url, 'size': size, 'digest': digest.split(':', 1)[1].lower()}}


def download_installer(release, destination_dir=None, timeout=30, opener=None):
    """Download an official release asset and verify its GitHub SHA-256 digest."""
    asset = release.get('asset') if isinstance(release, dict) else None
    if not isinstance(asset, dict):
        raise ValueError('更新信息缺少安装包')
    version = release.get('version', '')
    name, url, expected = asset.get('name'), asset.get('url'), asset.get('digest')
    parsed_version = version_tuple(version)
    expected_name = current_asset_name(version.lstrip('v')) if isinstance(version, str) else None
    if (not parsed_version or name != expected_name or not isinstance(url, str)
            or url != f'https://github.com/{REPOSITORY}/releases/download/{version}/{name}'
            or not isinstance(expected, str) or not re.fullmatch(r'[0-9a-f]{64}', expected)):
        raise ValueError('更新安装包来源无效')
    size = asset.get('size')
    if not isinstance(size, int) or size <= 0 or size > MAX_INSTALLER_BYTES:
        raise ValueError('更新安装包大小无效')
    root = os.path.abspath(destination_dir or os.path.join(tempfile.gettempdir(), 'DevotionFlow-updates'))
    os.makedirs(root, mode=0o700, exist_ok=True)
    fd, partial = tempfile.mkstemp(prefix='DevotionFlow-', suffix='.part', dir=root)
    target = os.path.join(root, name)
    request = Request(url, headers={'User-Agent': 'DevotionFlow-update', 'Accept': 'application/octet-stream'})
    digest = hashlib.sha256()
    received = 0
    try:
        with (opener or urlopen)(request, timeout=timeout) as response, os.fdopen(fd, 'wb') as output:
            final_url = response.geturl() if hasattr(response, 'geturl') else url
            if not final_url.startswith('https://') or not any(final_url.startswith(prefix) for prefix in (
                    'https://github.com/', 'https://release-assets.githubusercontent.com/',
                    'https://objects.githubusercontent.com/')):
                raise ValueError('更新下载被重定向到非官方地址')
            while True:
                block = response.read(1024 * 1024)
                if not block:
                    break
                received += len(block)
                if received > size or received > MAX_INSTALLER_BYTES:
                    raise ValueError('更新安装包超出声明大小')
                digest.update(block)
                output.write(block)
        if received != size or digest.hexdigest() != expected:
            raise ValueError('更新安装包校验失败，文件已丢弃')
        os.replace(partial, target)
        return target
    except Exception:
        try:
            os.close(fd)
        except OSError:
            pass
        try:
            os.remove(partial)
        except OSError:
            pass
        raise
