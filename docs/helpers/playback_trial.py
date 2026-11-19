"""Bound one measured playback attempt in a fresh visible browser."""

from __future__ import annotations

from .acceptance_playback_check import evaluate
from .youtube_telemetry import eligible, number

SECONDS = {"control": 120, "long": 900, "seek": 300}

# Use the standard media element. A rejected play() leaves the next observation
# paused. Do not await its promise: Chromium may leave it pending behind consent.
CONTROL = """({action, id, doc, seconds}) => {
    const v = document.querySelector('#movie_player video');
    if (location.origin !== 'https://www.youtube.com' ||
        new URL(location.href).searchParams.get('v') !== id ||
        performance.timeOrigin !== doc || document.hidden || !v || v.readyState < 1 ||
        document.querySelector('#movie_player.ad-showing, #movie_player.ad-interrupting'))
        return null;
    if (action === 'play') {
        if (v.paused && !v.ended) v.play().catch(() => {});
        return null;
    }
    let target = v.currentTime + 405;
    for (let i = 0; i < v.buffered.length; i++) {
        if (target >= v.buffered.start(i) && target <= v.buffered.end(i))
            target = v.buffered.end(i) + 5;
    }
    if (!(Number.isFinite(v.duration) && target + seconds + 10 < v.duration)) return null;
    v.currentTime = target;
    return target;
}"""


class PlaybackTrial:
    def __init__(self, phase, video):
        self.phase, self.video = phase, video
        self.minimum = SECONDS[phase]
        self.started = self.last_progress = self.last_play = None
        self.previous = self.context = self.seek_target = None
        self.first = None
        self.foregrounded = False
        self.verdict = None

    def step(self, page, rows):
        """Return a terminal reason, or continue. Keep the raw pre-start samples."""
        row = rows[-1]
        now = row["t_s"]
        if self.started is None:
            self.started = self.last_progress = now
        context = (row.get("document_id"), row.get("media_id"))
        same_video = row.get("video_id") == self.video and row.get("has_video") is True
        if self.context is not None and context != self.context and row.get("document_id"):
            return "player_replaced"
        if (row.get("video_id") == self.video and not row.get("ad") and (
                row.get("player_error_visible") or (same_video and row.get("error_code")))):
            return "player_error"
        if self.context and same_video and not row.get("ad") and row.get("playback_rate") != 1:
            return "playback_rate_changed"
        if row.get("hidden") and not self.foregrounded:
            page.bring_to_front()
            self.foregrounded = True
        ready = (same_video and not any(row.get(k) for k in ("ad", "hidden", "ended"))
                 and (row.get("ready_state") or 0) >= 1)
        if ready and row.get("paused") and self.context is None and (
                self.last_play is None or now - self.last_play >= 10):
            page.evaluate(CONTROL, {"action": "play", "id": self.video, "doc": context[0]})
            self.last_play = now
        prev, self.previous = self.previous, row
        if (prev and eligible(prev, self.video) and eligible(row, self.video)
                and (prev.get("document_id"), prev.get("media_id")) == context
                and row["playback_rate"] == prev["playback_rate"] == 1
                and 0 < now - prev["t_s"] <= 2.5
                and 0.05 < row["position"] - prev["position"] <= now - prev["t_s"] + 0.5):
            self.last_progress = now
            if self.context is None:
                self.context = context
                if self.phase == "seek":
                    self.seek_target = page.evaluate(CONTROL, {
                        "action": "seek", "id": self.video, "doc": context[0],
                        "seconds": self.minimum,
                    })
                    if not number(self.seek_target):
                        return "seek_unavailable"
                    self.seek_requested = now
                    row["requested_seek_position"] = self.seek_target
                else:
                    self.first = len(rows) - 1
        if self.seek_target is not None and self.first is None:
            for event in row.get("events", []):
                if (event.get("name") == "seeked" and event.get("media_id") == context[1]
                        and not event.get("ad") and not event.get("hidden")
                        and number(event.get("position"))
                        and abs(event["position"] - self.seek_target) <= 3):
                    self.first = len(rows) - 1
                    break
            if self.first is None and now - self.seek_requested >= 30:
                return "seek_unconfirmed"
        if (self.first is not None and now - rows[self.first]["t_s"] >= self.minimum
                and (self.verdict is None or now - self.last_check >= 5)):
            self.last_check = now
            self.verdict = evaluate(rows[self.first:], self.video, self.minimum,
                                    require_seek=self.phase == "seek")
            if self.verdict["ok"]:
                return "complete"
        if self.context is None and now - self.started >= 90:
            return "window_hidden" if row.get("hidden") else "start_unconfirmed"
        if self.context is not None and now - self.last_progress >= 45:
            if row.get("hidden"):
                return "window_hidden"
            if row.get("paused"):
                return "player_paused"
            return "playback_interrupted"
        return None

    def finish(self, rows, outcome):
        if self.first is not None:
            self.verdict = evaluate(rows[self.first:], self.video, self.minimum,
                                    require_seek=self.phase == "seek")
        return {"phase": self.phase, "outcome": outcome, "first_sample": self.first,
                "seek_target": self.seek_target, "measurement": self.verdict,
                "ok": outcome == "complete" and bool(self.verdict and self.verdict["ok"])}
