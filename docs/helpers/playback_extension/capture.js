(() => {
  if (globalThis.xgwPlaybackCapture) return;
  let run, timer;
  function stop() {
    clearInterval(timer);
    timer = undefined;
    return run;
  }
  globalThis.xgwPlaybackCapture = action => {
    if (action === "stop") return stop();
    const video = new URL(location.href).searchParams.get("v");
    if (timer !== undefined || !/^[A-Za-z0-9_-]{11}$/.test(video || "")) return false;
    const start = performance.now();
    run = {schema: 1, source: "chrome_extension", started_unix: Date.now() / 1000, rows: []};
    function sample() {
      const row = globalThis.__xgwTelemetry();
      const t = (performance.now() - start) / 1000;
      if (row.video_id !== video || t > 1800 || run.rows.length >= 1801) {
        stop();
        return;
      }
      run.rows.push({...row, t_s: t, unix: Date.now() / 1000});
    }
    timer = setInterval(sample, 1000);
    sample();
    return true;
  };
})();
