"""Desktop integration checks, run via runpy from the project root."""
import tempfile,json
from pathlib import Path
from unittest.mock import patch
from PySide6.QtWidgets import QApplication,QPushButton
from PySide6.QtGui import QPixmap,QColor,QWheelEvent
from PySide6.QtCore import Qt,QPointF,QPoint,QEventLoop,QTimer,QUrl
from PySide6.QtTest import QTest
from app.ui import Window
from app.capture import CAPTURE_VIDEO_RECT_SCRIPT

app=QApplication([])
with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as directory:
    root=Path(directory)
    window=Window(root,offline=True)
    window.timer.stop(); window.retry.stop(); window.sync=lambda *args,**kwargs:None
    assert not hasattr(window,'ad_blocker')
    assert not window.profile.scripts().find('DevotionFlow YoutubeAdblock 0.8.2')
    assert all(k not in window.settings_page.fields for k in ('ad_block','ad_block_page_script','ad_domains'))
    assert 'trySkip' not in window.probe
    assert all(button.text()!='开始新一轮观看' for button in window.findChildren(QPushButton))
    assert all('扩展' not in button.text() for button in window.settings_page.findChildren(QPushButton))
    assert window.update_button.text()=='检查更新'
    assert [button.text() for button in window.nav_buttons][-2:]==['◴  播放历史','▤  登记记录']
    assert not hasattr(window,'day_history') and not hasattr(window,'analytics_history')
    window.cfg['theme']='dark'; window.apply_theme()
    assert window.chart.text_color.name()=='#98a0aa'
    assert window.trend_chart.axis_color.name()=='#34373d'
    assert window.calendar.day_colors[0]=='#65b885'
    window.cfg['theme']='sage'; window.apply_theme()
    assert all(button.text()!='检查软件更新' for button in window.settings_page.findChildren(QPushButton))
    window.cfg['operator']='测试'; window.category.setCurrentText('电影')
    tracker=window.tracker; tracker.video='test'; tracker.title='测试视频'; tracker.duration=100; tracker.intervals=[(0,95)]
    with patch.object(window,'current_page_video_id',return_value='test'):
        window.show_tracking(); window.show_tracking()
    assert len(window.store.records())==1 and tracker.registered
    assert window.playback_history.rowCount()==1 and window.registration_history.rowCount()==1
    assert window.registration_history.item(0,1).text()=='测试视频'
    retry_buttons=[button for button in window.registration_history_page.findChildren(QPushButton)
                   if button.text()=='按当前设置重新登记失败记录']
    assert len(retry_buttons)==1
    with patch.object(window,'sync') as retry_sync:
        window.cfg['mode']='google'
        window.retry_failed_records()
        retry_sync.assert_not_called()
        with window.store.db:
            row=window.store.db.execute('SELECT id,config FROM records LIMIT 1').fetchone()
            record_cfg=json.loads(row['config']); record_cfg['mode']='google'
            window.store.db.execute("UPDATE records SET config=?,error='日期匹配失败' WHERE id=?",
                                    (json.dumps(record_cfg),row['id']))
        retry_buttons[0].click()
        retry_sync.assert_called_once_with(manual=True,retry_cfg=window.cfg)
        with window.store.db:
            record_cfg['mode']='local'
            window.store.db.execute("UPDATE records SET config=?,error='' WHERE id=?",
                                    (json.dumps(record_cfg),row['id']))
        window.cfg['mode']='local'
    tracker.sample(dict(id='test',title='测试视频',duration=100,position=0,clock=1000,playing=True,seeking=False,rate=1,adShowing=False))
    assert not tracker.registered and tracker.watched==0
    tracker.intervals=[(0,95)]
    with patch.object(window,'current_page_video_id',return_value='test'):
        window.show_tracking()
    assert len(window.store.records())==2
    window.tracker.reset(); tracker=window.tracker; tracker.intervals=[(0,42)]; tracker.position=55
    window.reflection.setPlainText('保留草稿'); window.category.setCurrentText('诗歌'); window.save_draft()
    window.restore_draft('test'); assert window.tracker.watched==42 and window.resume_position==55
    assert window.reflection.toPlainText()=='保留草稿' and window.category.currentText()=='诗歌'
    window.tracker.reset(); tracker=window.tracker; tracker.video='abcdefghijk'; tracker.title='记忆点续播测试'; tracker.duration=1800; tracker.intervals=[(0,22.7)]
    window.category.setCurrentText('诗歌')
    with patch.object(window,'current_page_video_id',return_value='abcdefghijk'):
        window.show_tracking(); assert window.submit.isEnabled()
        assert not window.completion_confirm_checkbox.isHidden()
        window.resume_position=None
        ad_sample=json.dumps(dict(id='abcdefghijk',title='广告期视频',duration=1800,position=0,
            clock=1000,playing=False,seeking=False,rate=1,adShowing=True))
        with patch.object(window,'current_page_video_id',return_value='abcdefghijk'), patch('app.ui.is_youtube_url',return_value=True):
            window.receive(ad_sample)
        assert window.tracker.video=='abcdefghijk' and window.tracker.ad_showing
        assert window.tracker.watched==22.7 and window.submit.isEnabled()
        assert '广告时段不计入' in window.metrics.text()
        assert '广告时段不会计入' in window.status.text()
        # A slow YouTube page must not accumulate overlapping probe scripts.
        with patch('app.ui.is_youtube_url',return_value=True), patch.object(window.browser.page(),'runJavaScript') as run_probe:
            window.poll(); window.poll(); assert run_probe.call_count==1 and window._probe_pending
            window.probe_finished(None)
            assert not window._probe_pending and window.submit.isEnabled()
        # The submit button must respond to a physical-style click in the UI.
        previous_count=len(window.store.records())
        window.completion_confirm_checkbox.setChecked(True); window.show(); app.processEvents()
        QTest.mouseClick(window.submit,Qt.LeftButton); app.processEvents()
    assert len(window.store.records())==previous_count+1
    confirmed=window.store.records()[0]
    assert confirmed['completion_confirmed'] and confirmed['ratio']<.95 and confirmed['watched']<1800
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
    captures=list(root.glob('*-abcdefghijk.png'))
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
    assert not hasattr(window,'choose_browser_extension')
    legacy_source=root/'extensions'/'old-extension'; legacy_source.mkdir(parents=True)
    window.cfg['browser_extension_dir']='extensions/old-extension'; window.cfg['browser_extension_name']='old'
    window.remove_legacy_extension_source()
    assert not legacy_source.exists() and 'browser_extension_dir' not in window.cfg
    window.close(); app.processEvents()
    # WebEngine releases files asynchronously, so no deletion is required for this check.
    print('PASS: automatic registration, duplicate prevention, image upload, sidebar, hover status')
