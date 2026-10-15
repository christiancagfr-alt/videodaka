"""Exercise installed yt-dlp + FFmpeg against a local test video."""
import functools
import http.server
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading
from app.downloads import download_arguments

with tempfile.TemporaryDirectory() as folder:
    root=Path(folder); video=root/'fixture.mp4'; output=root/'output'; output.mkdir()
    subprocess.run([shutil.which('ffmpeg'),'-hide_banner','-loglevel','error','-f','lavfi','-i','color=c=green:s=320x180:d=1','-f','lavfi','-i','sine=frequency=440:duration=1','-c:v','mpeg4','-c:a','aac','-shortest',str(video)],check=True)
    server=http.server.ThreadingHTTPServer(('127.0.0.1',0),functools.partial(http.server.SimpleHTTPRequestHandler,directory=str(root)))
    thread=threading.Thread(target=server.serve_forever,daemon=True); thread.start()
    try:
        # Direct MP4 responses have no extractor-reported height, so use source quality.
        args=download_arguments(f'http://127.0.0.1:{server.server_port}/fixture.mp4',output,'best')
        first=subprocess.run([sys.executable,*args],capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=60)
        assert first.returncode==0,first.stderr
        assert list(output.glob('*.mp4'))
        second=subprocess.run([sys.executable,*args],capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=60)
        assert second.returncode==0 and 'archive' in second.stdout
        print('PASS: real yt-dlp download and archive deduplication; local fixture only')
    finally: server.shutdown(); server.server_close()
