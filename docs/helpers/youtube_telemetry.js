// Read-only probe. No playback commands, undocumented player APIs or URL/body export.
(() => {
  if (window.__xgwTelemetry) return;
  let video = null, serial = 0;
  const events = [];
  let overflow = 0;
  const ad = () => !!document.querySelector('#movie_player.ad-showing, #movie_player.ad-interrupting');
  const attach = () => {
    const current = document.querySelector('#movie_player video');
    if (!current || current === video) return;
    video = current;
    const id = ++serial;
    for (const name of ['play', 'playing', 'waiting', 'stalled', 'pause', 'seeking',
                        'seeked', 'ended', 'error', 'emptied', 'loadedmetadata']) {
      current.addEventListener(name, () => {
        if (events.length >= 256) { events.shift(); overflow++; }
        events.push({name, at_ms: performance.now(), media_id: id,
          position: current.currentTime, ad: ad(), paused: current.paused,
          seeking: current.seeking, hidden: document.hidden});
      });
    }
  };
  new MutationObserver(attach).observe(document, {subtree: true, childList: true});
  window.__xgwTelemetry = () => {
    attach();
    const v = document.querySelector('#movie_player video');
    const stats = {};
    // Optional English/Russian overlay. Missing/changed markup leaves these fields absent.
    for (const key of document.querySelectorAll('.html5-video-info-panel-key')) {
      const label = key.textContent.trim();
      const value = key.parentElement.querySelector('.html5-video-info-panel-value');
      if (!value) continue;
      const text = value.textContent.trim();
      if (/^(Connection Speed|Скорость соединения)$/i.test(label)) {
        const match = text.match(/([\d.,]+)\s*(Kbps|Кбит\/с)/i);
        if (match) stats.connection_kbps = Number(match[1].replace(',', '.'));
      }
      if (/^(Buffer Health|Состояние буфера|Объем буфера|Объём буфера)$/i.test(label)) {
        const match = text.match(/^[\d.,]+/);
        if (match) stats.buffer_seconds = Number(match[0].replace(',', '.'));
      }
      if (/^(Codecs|Кодеки)$/i.test(label) && /^[\w. ()/,-]{1,120}$/.test(text)) {
        stats.codecs = text;
      }
    }
    const requested = new URL(location.href).searchParams.get('v') || '';
    const base = {document_id: performance.timeOrigin, media_id: serial,
      at_ms: performance.now(), video_id: /^[\w-]{11}$/.test(requested) ? requested : null,
      has_video: !!v, ad: ad(), hidden: document.hidden,
      events: events.splice(0), event_overflow: overflow, stats};
    if (!v) return base;
    let buffer = 0;
    for (let i = 0; i < v.buffered.length; i++) {
      if (v.buffered.start(i) <= v.currentTime && v.currentTime < v.buffered.end(i)) {
        buffer = v.buffered.end(i) - v.currentTime;
        break;
      }
    }
    const q = v.getVideoPlaybackQuality ? v.getVideoPlaybackQuality() : null;
    return {...base, position: v.currentTime, paused: v.paused, seeking: v.seeking,
      ended: v.ended, ready_state: v.readyState, playback_rate: v.playbackRate,
      width: v.videoWidth, height: v.videoHeight, buffer_seconds: buffer,
      total_frames: q ? q.totalVideoFrames : null,
      dropped_frames: q ? q.droppedVideoFrames : null,
      error_code: v.error ? v.error.code : null, muted: v.muted, volume: v.volume};
  };
})();
