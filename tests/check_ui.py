"""Desktop integration checks, run via runpy from the project root."""
import tempfile,json
from pathlib import Path
from unittest.mock import patch
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QPixmap,QColor,QWheelEvent
from PySide6.QtCore import Qt,QPointF,QPoint,QEventLoop,QTimer,QUrl
from app.ui import Window
from app.capture import CAPTURE_VIDEO_RECT_SCRIPT,seek_video_script

app=QApplication([])
with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as directory:
    root=Path(directory)
    window=Window(root,offline=True)
    window.timer.stop(); window.retry.stop(); window.sync=lambda:None
    window.cfg['operator']='测试'; window.category.setCurrentText('电影')
    tracker=window.tracker; tracker.video='test'; tracker.duration=100; tracker.intervals=[(0,95)]
    window.show_tracking(); window.show_tracking()
    assert len(window.store.records())==1 and tracker.registered
    window.new_round(); tracker.intervals=[(0,95)]; window.show_tracking()
    assert len(window.store.records())==2
    window.new_round(); tracker=window.tracker; tracker.intervals=[(0,42)]; tracker.position=55
    window.reflection.setPlainText('保留草稿'); window.category.setCurrentText('诗歌'); window.save_draft()
    window.restore_draft('test'); assert window.tracker.watched==42 and window.resume_position==55
    assert window.reflection.toPlainText()=='保留草稿' and window.category.currentText()=='诗歌'
    picture=QPixmap(80,80); picture.fill(QColor('green')); source=root/'input.png'; picture.save(str(source))
    with patch('app.ui.QFileDialog.getOpenFileName',return_value=(str(source),'PNG')):
        window.settings_page.choose_avatar()
    selected=window.settings_page.fields['avatar_path'].text()
    assert Path(selected).exists() and selected!=str(source)
    window.cfg['avatar_path']=selected; window.refresh(); assert not window.avatar.icon().isNull()
    window.show(); window.toggle_sidebar(); assert window.sidebar.isHidden()
    window.enter_fullscreen(); window.exit_fullscreen(); assert window.sidebar.isHidden()
    window.toggle_sidebar(); assert not window.sidebar.isHidden()
    assert '观看进度' in window.avatar.toolTip() and '健康值' in window.avatar.toolTip()
    window.select_page(3)
    assert window.settings_page.back_to_player is not None
    window.settings_page.back_to_player.click()
    assert window.pages.currentIndex()==0
    window.category.clearFocus(); original=window.category.currentText()
    wheel=QWheelEvent(QPointF(5,5),QPointF(5,5),QPoint(0,0),QPoint(0,-120),Qt.NoButton,Qt.NoModifier,Qt.NoScrollPhase,False)
    window.category.wheelEvent(wheel); assert window.category.currentText()==original and not wheel.isAccepted()
    window.cfg['screenshot_dir']=str(root)
    scale=window.browser.grab().width()/window.browser.width()
    window.save_video_frame({'x':10,'y':10,'w':80,'h':60,'playing':False},automatic=False)
    wait=QEventLoop(); QTimer.singleShot(250,wait.quit); wait.exec()
    captures=list(root.glob('*-test.png'))
    assert len(captures)==1
    shot=QPixmap(str(captures[0]))
    assert shot.width()==round(80*scale) and shot.height()==round(60*scale)
    # A YouTube-style video container remains capturable before videoWidth metadata is available.
    ready=QEventLoop(); window.browser.loadFinished.connect(lambda _ok:ready.quit())
    window.browser.setHtml('<html><body><div class="html5-video-container" style="position:fixed;left:25px;top:30px;width:160px;height:90px"><video style="width:100%;height:100%"></video></div></body></html>')
    QTimer.singleShot(3000,ready.quit); ready.exec()
    result=[]; loop=QEventLoop()
    window.browser.page().runJavaScript(CAPTURE_VIDEO_RECT_SCRIPT,lambda value:(result.append(json.loads(value) if isinstance(value,str) and value else value),loop.quit()))
    QTimer.singleShot(3000,loop.quit); loop.exec()
    assert result and isinstance(result[0],dict) and result[0].get('w')==160 and result[0].get('h')==90, result
    # Resume probing must prefer the visible, actively playing video over a stale hidden player.
    probe=(Path(__file__).resolve().parents[1]/'app'/'probe.js').read_text('utf-8')
    fixture='<div style="position:fixed;left:25px;top:30px;width:100px;height:50px"><video id="stale" style="width:100%;height:100%"></video></div><div style="position:fixed;left:150px;top:30px;width:160px;height:90px"><video id="active" style="width:100%;height:100%"></video></div>'
    ready=QEventLoop(); window.browser.loadFinished.connect(lambda _ok:ready.quit())
    window.browser.setHtml('<html><body>'+fixture+'</body></html>',QUrl('https://www.youtube.com/watch?v=fixture'))
    QTimer.singleShot(3000,ready.quit); ready.exec()
    setup="""(()=>{const [stale,active]=document.querySelectorAll('video');for(const [v,time,playing,ready] of [[stale,5,false,0],[active,25,true,4]]){Object.defineProperties(v,{duration:{value:100,configurable:true},currentTime:{value:time,writable:true,configurable:true},paused:{value:!playing,writable:true,configurable:true},readyState:{value:ready,configurable:true}})}})()"""
    window.browser.page().runJavaScript(setup)
    sampled=[]; loop=QEventLoop(); window.browser.page().runJavaScript(probe,lambda value:(sampled.append(json.loads(value) if value else None),loop.quit()))
    QTimer.singleShot(1000,loop.quit); loop.exec()
    assert sampled and sampled[0]['position']==25 and sampled[0]['playing']
    seeked=[]; loop=QEventLoop(); window.browser.page().runJavaScript(seek_video_script(40),lambda _value:(window.browser.page().runJavaScript("JSON.stringify({position:document.querySelector('#active').currentTime,paused:document.querySelector('#active').paused})",lambda value:(seeked.append(json.loads(value)),loop.quit()))))
    QTimer.singleShot(1000,loop.quit); loop.exec()
    assert seeked and seeked[0]=={'position':40,'paused':False}, seeked
    ffmpeg=root/'ffmpeg.exe'; ffmpeg.write_bytes(b'fixture')
    with patch('app.downloads.find_ffmpeg',return_value=str(ffmpeg)):
        window.open_download_settings()
        assert window.download_dialog.ffmpeg_field.text()==str(ffmpeg)
        assert window.cfg['ffmpeg_path']==str(ffmpeg)
        with patch.object(window.download_dialog,'install_ffmpeg') as installer:
            window.download_dialog.ffmpeg_install_button.click()
            installer.assert_called_once_with('',resume_download=False)
    window.download_dialog.settings_dialog.close(); app.processEvents()
    window.close(); app.processEvents()
    # WebEngine releases files asynchronously, so no deletion is required for this check.
    print('PASS: automatic registration, duplicate prevention, image upload, sidebar, hover status')
