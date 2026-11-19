const status = document.getElementById("status");
const save = document.getElementById("save");
let blobURL;

async function record(command) {
  try {
    const [tab] = await chrome.tabs.query({active: true, currentWindow: true});
    if (!tab?.url || !tab.url.startsWith("https://www.youtube.com/watch?")) {
      status.textContent = "Откройте страницу ролика YouTube.";
      return;
    }
    const target = {tabId: tab.id};
    if (command === "start") {
      await chrome.scripting.executeScript({
        target, world: "ISOLATED", files: ["youtube_telemetry.js", "capture.js"],
      });
    }
    const [{result}] = await chrome.scripting.executeScript({
      target, world: "ISOLATED",
      func: action => globalThis.xgwPlaybackCapture?.(action),
      args: [command],
    });
    if (command === "start") {
      save.hidden = true;
      status.textContent = result === true ? "Запись идёт в этой вкладке." :
        "Запись уже идёт или ролик недоступен.";
    } else if (result?.rows?.length) {
      if (blobURL) URL.revokeObjectURL(blobURL);
      blobURL = URL.createObjectURL(new Blob([JSON.stringify(result)], {type: "application/json"}));
      save.href = blobURL;
      save.download = "xgw-player-" + Math.round(result.started_unix) + ".json";
      save.hidden = false;
      status.textContent = "Запись готова. Сохраните файл.";
    } else {
      status.textContent = "В этой вкладке нет записи.";
    }
  } catch {
    status.textContent = "Не удалось прочитать запись из вкладки.";
  }
}

document.getElementById("start").onclick = () => record("start");
document.getElementById("stop").onclick = () => record("stop");
