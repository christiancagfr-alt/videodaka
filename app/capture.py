"""Read the visible YouTube video bounds without changing page styles."""
import math

CAPTURE_VIDEO_RECT_SCRIPT = r'''(function () {
 try {
  var video=document.querySelector('video');
  if(!video) return JSON.stringify({captureError:'not-found'});
  var style=getComputedStyle(video),rect=video.getBoundingClientRect();
  if(style.display==='none'||style.visibility==='hidden'||rect.width<=0||rect.height<=0) return JSON.stringify({captureError:'not-visible'});
  var x=Math.max(0,rect.left),y=Math.max(0,rect.top),right=Math.min(innerWidth,rect.right),bottom=Math.min(innerHeight,rect.bottom);
  if(right<=x||bottom<=y) return JSON.stringify({captureError:'not-visible'});
  return JSON.stringify({x:x,y:y,w:right-x,h:bottom-y,playing:!video.paused&&!video.ended});
 } catch(error) { return JSON.stringify({captureError:'exception',message:String(error)}); }
})()'''

def seek_video_script(position):
    """Resume the current YouTube video without changing its play/pause state."""
    position=float(position)
    if not math.isfinite(position) or position<0: raise ValueError('Invalid resume position')
    return f'''(function(){{var video=document.querySelector('video');if(video)video.currentTime={position!r};}})()'''
