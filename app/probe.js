(() => {
 const root = window;
 const host = root.location.hostname;
 if (root.location.protocol !== 'https:' || !['youtube.com','www.youtube.com','m.youtube.com','music.youtube.com'].includes(host)) return JSON.stringify(null);
 const url = new URL(root.location.href);
 const id = url.searchParams.get('v') || (url.pathname.startsWith('/shorts/') ? url.pathname.split('/')[2] : '');
 if (!id || root.document.querySelector('.ad-showing')) return JSON.stringify(null);

 const chooseVideo = (doc, depth=0) => {
  if (!doc || depth > 5) return null;
  let videos=[];
  try { videos=[...doc.querySelectorAll('video')]; } catch (_) { return null; }
  const candidates=videos.map(video => {
   try {
    const style=doc.defaultView.getComputedStyle(video);
    const viewport=video.closest('.html5-video-container') || video;
    const rect=viewport.getBoundingClientRect();
    if (style.display==='none' || style.visibility==='hidden' || Number(style.opacity)===0 || rect.width<32 || rect.height<32) return null;
    return {video,area:rect.width*rect.height,playing:!video.paused&&!video.ended,ready:video.readyState>=2};
   } catch (_) { return null; }
  }).filter(Boolean);
  candidates.sort((a,b)=>Number(b.playing)-Number(a.playing)||Number(b.ready)-Number(a.ready)||b.area-a.area);
  if (candidates.length) return candidates[0].video;
  let frames=[];
  try { frames=[...doc.querySelectorAll('iframe')]; } catch (_) { return null; }
  for (const frame of frames) {
   try {
    const rect=frame.getBoundingClientRect();
    if (rect.width>=32 && rect.height>=32) {
     const child=chooseVideo(frame.contentDocument,depth+1);
     if (child) return child;
    }
   } catch (_) {}
  }
  return null;
 };
 const video=chooseVideo(root.document);
 if (!video || !Number.isFinite(video.duration)) return JSON.stringify(null);
 return JSON.stringify({id,title:root.document.querySelector('h1.ytd-watch-metadata')?.innerText || root.document.title.replace(/ - YouTube$/, ''),
  duration:video.duration,position:video.currentTime,clock:performance.now(),playing:!video.paused&&!video.ended&&video.readyState>=2,
  seeking:video.seeking,rate:video.playbackRate});
})()
