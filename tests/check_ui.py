"""Desktop integration checks, run via runpy from the project root."""
import tempfile
from pathlib import Path
from unittest.mock import patch
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QPixmap,QColor,QWheelEvent
from PySide6.QtCore import Qt,QPointF,QPoint,QEventLoop,QTimer
from app.ui import Window

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
    window.close(); app.processEvents()
    # WebEngine releases files asynchronously, so no deletion is required for this check.
    print('PASS: automatic registration, duplicate prevention, image upload, sidebar, hover status')
