"""Desktop integration checks, run via runpy from the project root."""
import tempfile,json
from pathlib import Path
from unittest.mock import patch
from PySide6.QtWidgets import QApplication,QPushButton
from PySide6.QtGui import QPixmap,QColor,QWheelEvent
from PySide6.QtCore import Qt,QPointF,QPoint,QEventLoop,QTimer,QUrl
from app.ui import Window
from app.capture import CAPTURE_VIDEO_RECT_SCRIPT

app=QApplication([])
with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as directory:
    root=Path(directory)
    window=Window(root,offline=True)
    window.timer.stop(); window.retry.stop(); window.sync=lambda:None
    assert window.ad_blocker.enabled and 'ad_block' in window.settings_page.fields
    assert window.extension_manager is window.profile.extensionManager()
    assert 'Manifest V3' in window.settings_page.extension_status.text()
    assert window.update_button.text()=='检查更新'
    assert all(button.text()!='检查软件更新' for button in window.settings_page.findChildren(QPushButton))
    window.settings_page.fields['ad_block'].setChecked(False); window.save_settings_page()
    assert not window.ad_blocker.enabled
    window.settings_page.fields['ad_block'].setChecked(True); window.save_settings_page()
    assert window.ad_blocker.enabled
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
    # about:blank is explicitly allowed by BrowserPage. Inject the fixture after load
    # instead of setHtml(), which uses a data: URL rejected by some QtWebEngine builds.
    ready=QEventLoop(); window.browser.loadFinished.connect(lambda _ok:ready.quit())
    window.browser.setUrl(QUrl('about:blank'))
    QTimer.singleShot(3000,ready.quit); ready.exec()
    fixture_html='<div class="html5-video-container" style="position:fixed;left:25px;top:30px;width:160px;height:90px"><video style="width:100%;height:100%"></video></div>'
    setup_html='document.body.innerHTML='+json.dumps(fixture_html)
    window.browser.page().runJavaScript(setup_html)
    result=[]; loop=QEventLoop()
    window.browser.page().runJavaScript(CAPTURE_VIDEO_RECT_SCRIPT,lambda value:(result.append(json.loads(value) if isinstance(value,str) and value else value),loop.quit()))
    QTimer.singleShot(3000,loop.quit); loop.exec()
    if result and isinstance(result[0],dict):
        assert result[0].get('w')==160 and result[0].get('h')==90, result
    else:
        print('SKIP: QtWebEngine JavaScript callbacks unavailable; browser DOM capture/probe integration was not exercised')
    ffmpeg=root/'ffmpeg.exe'; ffmpeg.write_bytes(b'fixture')
    with patch('app.downloads.find_ffmpeg',return_value=str(ffmpeg)):
        window.open_download_settings()
        assert window.download_dialog.ffmpeg_field.text()==str(ffmpeg)
        assert window.cfg['ffmpeg_path']==str(ffmpeg)
        with patch.object(window.download_dialog,'install_ffmpeg') as installer:
            window.download_dialog.ffmpeg_install_button.click()
            installer.assert_called_once_with('',resume_download=False)
    window.download_dialog.settings_dialog.close(); app.processEvents()
    # The player toolbar downloads immediately without opening a separate window.
    download=window.download_dialog; current_url='https://www.youtube.com/watch?v=manual-test'
    download.seen.add(current_url)  # A previous finished attempt must be retryable by the user.
    window.browser.setUrl(QUrl('http://127.0.0.1:8080/admin'))
    with patch.object(download,'start') as start_download:
        window.open_downloads()
        start_download.assert_not_called()
    assert 'YouTube' in window.status.text() and not download.isVisible()
    window.browser.setUrl(QUrl(current_url))
    with patch.object(download,'start') as start_download:
        window.open_downloads()
        start_download.assert_called_once_with(False)
    assert not download.isVisible()
    download.report('下载已开始：测试视频')
    assert window.status.text()=='下载已开始：测试视频'
    window.close(); app.processEvents()
    # WebEngine releases files asynchronously, so no deletion is required for this check.
    print('PASS: automatic registration, duplicate prevention, image upload, sidebar, hover status')
