(() => {
 if (location.protocol !== 'https:' || !['youtube.com','www.youtube.com','m.youtube.com','music.youtube.com'].includes(location.hostname)) return JSON.stringify(null);
 const video = document.querySelector('video');
 const url = new URL(location.href);
 const id = url.searchParams.get('v') || (url.pathname.startsWith('/shorts/') ? url.pathname.split('/')[2] : '');
 if (!video || !id) return JSON.stringify(null);
 const adShowing = Boolean(document.querySelector('.ad-showing'));
 // During an in-stream ad the <video> duration/position describe the ad.
 // Prefer YouTube's content metadata so the journal stays populated without
 // crediting the ad as watched content.
 const details = window.ytInitialPlayerResponse?.videoDetails;
 const playerArgs = window.ytplayer?.config?.args;
 const responseDuration = details?.videoId === id ? Number(details.lengthSeconds) : 0;
 const argsDuration = playerArgs?.video_id === id ? Number(playerArgs.length_seconds) : 0;
 const configuredDuration = Math.max(responseDuration, argsDuration);
 const mediaDuration = Number.isFinite(video.duration) ? video.duration : 0;
 const duration = configuredDuration > 0 ? configuredDuration : (adShowing ? 0 : mediaDuration);
 const metaDuration = document.querySelector('meta[itemprop="duration"]')?.content || '';
 const parsedMeta = /^PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+(?:\.\d+)?)S)?$/i.exec(metaDuration);
 const durationFromMeta = parsedMeta ? Number(parsedMeta[1] || 0)*3600 + Number(parsedMeta[2] || 0)*60 + Number(parsedMeta[3] || 0) : 0;
 const contentDuration = duration || durationFromMeta;
 return JSON.stringify({id, title:document.querySelector('h1.ytd-watch-metadata')?.innerText || document.title.replace(/ - YouTube$/, ''),
  duration:contentDuration, position:adShowing ? 0 : video.currentTime,
  clock:performance.now(), playing:!adShowing && !video.paused && !video.ended && video.readyState>=3,
  seeking:!adShowing && video.seeking, rate:adShowing ? 1 : video.playbackRate, adShowing});
})()
