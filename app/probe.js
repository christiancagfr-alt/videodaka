(() => {
 if (location.protocol !== 'https:' || !['youtube.com','www.youtube.com','m.youtube.com','music.youtube.com'].includes(location.hostname)) return JSON.stringify(null);
 // Clicking YouTube's own enabled skip control is safer than cancelling media
 // requests, since in-stream ads can share the same CDN as the actual video.
 if (!window.__devotionFlowSkipObserver) {
  window.__devotionFlowSkipObserver = true;
  const trySkip = () => {
   const button = document.querySelector('button.ytp-ad-skip-button, button.ytp-ad-skip-button-modern, button.ytp-skip-ad-button');
   if (!button || button.disabled || button.dataset.devotionFlowSkipAttempted === 'true' || button.getAttribute('aria-disabled') === 'true') return;
   const style = getComputedStyle(button), rect = button.getBoundingClientRect();
   if (style.display !== 'none' && style.visibility !== 'hidden' && rect.width > 0 && rect.height > 0) {
    button.dataset.devotionFlowSkipAttempted = 'true';
    button.click();
   }
  };
  trySkip();
  window.__devotionFlowSkipTimer = setInterval(trySkip, 1000);
 }
 const video = document.querySelector('video');
 const url = new URL(location.href);
 const id = url.searchParams.get('v') || (url.pathname.startsWith('/shorts/') ? url.pathname.split('/')[2] : '');
 if (!video || !id || document.querySelector('.ad-showing')) return JSON.stringify(null);
 return JSON.stringify({id, title:document.querySelector('h1.ytd-watch-metadata')?.innerText || document.title.replace(/ - YouTube$/, ''),
  duration:Number.isFinite(video.duration)?video.duration:0, position:video.currentTime,
  clock:performance.now(), playing:!video.paused && !video.ended && video.readyState>=3,
  seeking:video.seeking, rate:video.playbackRate});
})()
