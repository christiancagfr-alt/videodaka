"""Locate video-only capture bounds and keep resume seeking on the visible player."""
import math

CAPTURE_VIDEO_RECT_SCRIPT = r'''(function () {
 try {
  function intersect(a, b) {
    var x = Math.max(a.x, b.x), y = Math.max(a.y, b.y);
    var right = Math.min(a.right, b.right), bottom = Math.min(a.bottom, b.bottom);
    return right > x && bottom > y ? {x:x, y:y, right:right, bottom:bottom} : null;
  }
  function findVideo(doc, dx, dy, clip, depth) {
    if (!doc || depth > 5) return null;
    var videos = doc.getElementsByTagName('video');
    for (var i=0; i<videos.length; i++) {
      var video = videos[i], style = doc.defaultView.getComputedStyle(video);
      if (style.display === 'none' || style.visibility === 'hidden' || parseFloat(style.opacity) === 0) continue;
      var box = video.closest('.html5-video-container') || video;
      var rect = box.getBoundingClientRect();
      if (rect.width < 32 || rect.height < 32) continue;
      var visible = intersect(clip, {x:dx+rect.left, y:dy+rect.top, right:dx+rect.right, bottom:dy+rect.bottom});
      if (visible) return {x:visible.x, y:visible.y, w:visible.right-visible.x, h:visible.bottom-visible.y,
        playing:!video.paused && !video.ended};
    }
    var frames = doc.getElementsByTagName('iframe');
    for (var j=0; j<frames.length; j++) {
      var frame=frames[j], frameRect=frame.getBoundingClientRect();
      if (frameRect.width < 32 || frameRect.height < 32) continue;
      var absolute={x:dx+frameRect.left, y:dy+frameRect.top, right:dx+frameRect.right, bottom:dy+frameRect.bottom};
      var visibleFrame=intersect(clip,absolute);
      if (!visibleFrame) continue;
      try {
        var found=findVideo(frame.contentDocument,dx+frameRect.left,dy+frameRect.top,visibleFrame,depth+1);
        if (found) return found;
      } catch (_) {}
    }
    return null;
  }
  var result=findVideo(document,0,0,{x:0,y:0,right:innerWidth,bottom:innerHeight},0);
  if (!result) return JSON.stringify({captureError:'not-found'});
  return JSON.stringify(result);
 } catch (error) { return JSON.stringify({captureError:'exception',message:String(error)}); }
})()'''

def seek_video_script(position):
    """Seek the visible player without pausing a video that is already playing."""
    position=float(position)
    if not math.isfinite(position) or position<0: raise ValueError('Invalid resume position')
    return f'''(function(){{
      function find(doc,depth){{
        if(!doc||depth>5)return null;
        var videos=doc.getElementsByTagName('video'),candidates=[];
        for(var i=0;i<videos.length;i++){{
          var video=videos[i],style=doc.defaultView.getComputedStyle(video),box=video.closest('.html5-video-container')||video,rect=box.getBoundingClientRect();
          if(style.display!=='none'&&style.visibility!=='hidden'&&parseFloat(style.opacity)!==0&&rect.width>=32&&rect.height>=32)candidates.push(video);
        }}
        candidates.sort(function(a,b){{return Number(!b.paused)-Number(!a.paused)||Number(b.readyState>=2)-Number(a.readyState>=2);}});
        if(candidates.length)return candidates[0];
        var frames=doc.getElementsByTagName('iframe');
        for(var j=0;j<frames.length;j++){{try{{var video=find(frames[j].contentDocument,depth+1);if(video)return video;}}catch(_){{}}}}
        return null;
      }}
      var video=find(document,0);if(video)video.currentTime={position!r};
    }})()'''
