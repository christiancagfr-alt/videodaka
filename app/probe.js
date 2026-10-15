(() => {
 if (location.protocol !== 'https:' || !['youtube.com','www.youtube.com','m.youtube.com','music.youtube.com'].includes(location.hostname)) return JSON.stringify(null);
 const video = document.querySelector('video');
 const url = new URL(location.href);
 const id = url.searchParams.get('v') || (url.pathname.startsWith('/shorts/') ? url.pathname.split('/')[2] : '');
 if (!video || !id || document.querySelector('.ad-showing')) return JSON.stringify(null);
 return JSON.stringify({id, title:document.querySelector('h1.ytd-watch-metadata')?.innerText || document.title.replace(/ - YouTube$/, ''),
  duration:Number.isFinite(video.duration)?video.duration:0, position:video.currentTime,
  clock:performance.now(), playing:!video.paused && !video.ended && video.readyState>=3,
  seeking:video.seeking, rate:video.playbackRate});
})()
