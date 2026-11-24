"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

const source = fs.readFileSync(path.join(__dirname, "../src/xgw/ui/zapret2.js"), "utf8");

function page() {
  const listeners = new Map();
  const button = {
    addEventListener: (event, callback) => listeners.set(event, callback),
  };
  const makeElement = () => ({
    events: {},
    addEventListener(event, callback) { this.events[event] = callback; },
    querySelector() { return this; },
    focus() {},
    reportValidity() { return true; },
    dataset: {},
    replaceChildren(...children) { this.children = children; },
    append(...children) { this.children = children; },
  });
  const elements = new Map();
  const element = id => {
    if (!elements.has(id)) elements.set(id, makeElement());
    return elements.get(id);
  };
  const document = {
    hidden: false,
    documentElement: {dataset: {}},
    getElementById: id => id === "retry-overview" ? button : element(id),
    createElement: makeElement,
    querySelectorAll: () => [],
    addEventListener: (event, callback) => listeners.set(event, callback),
  };
  const requests = [];
  const timers = new Map();
  let nextTimer = 0;
  const context = vm.createContext({
    AbortController,
    document,
    window: {addEventListener: (event, callback) => listeners.set(event, callback)},
    localStorage: {getItem: () => null},
    fetch: (url, options) => new Promise(resolve => {
      assert.equal(url, "/api/zapret2/overview");
      assert.equal(options.method ?? "GET", "GET");
      requests.push(status => resolve({
        status, ok: status === 200, json: async () => ({}),
      }));
    }),
    setTimeout: (callback, delay) => {
      timers.set(++nextTimer, {callback, delay});
      return nextTimer;
    },
    clearTimeout: id => timers.delete(id),
  });
  vm.runInContext(source, context);
  vm.runInContext("render = () => { online = true; controls(); };", context);
  return {
    requests,
    button,
    element,
    evaluate: script => vm.runInContext(script, context),
    emit: event => listeners.get(event)(),
    visibility(hidden) {
      document.hidden = hidden;
      listeners.get("visibilitychange")();
    },
    delays: () => [...timers.values()].map(timer => timer.delay),
    runTimer(delay) {
      const [id, timer] = [...timers].find(([, timer]) => timer.delay === delay);
      timers.delete(id);
      timer.callback();
    },
  };
}

const settle = () => new Promise(resolve => setImmediate(resolve));

test("ALT9 form only writes changed exclusions while the backend allows editing", () => {
  const browser = page();
  browser.evaluate(`
    online = true;
    latest = {mode: "off", can_edit: true, can_edit_flowseal_exclusions: true,
      selected_strategy: "flowseal_alt9", config_key: "initial",
      strategies: ["multisplit"], domains: ["domain:youtube.com", "domain:googlevideo.com"],
      flowseal_exclude_domains: ["saved.youtube.com"], check_seconds: 180, retry_seconds: 300,
      daily_probe_mb: 256};
    command = (action, body) => { sent = {action, body}; };
    openSettings();
  `);
  const field = browser.element("setting-flowseal-exclusions");
  const form = browser.element("settings-form");
  const submit = () => {
    form.events.submit({preventDefault() {}, currentTarget: form});
    return JSON.parse(browser.evaluate("JSON.stringify(sent)"));
  };
  assert.equal(browser.element("flowseal-exclusion-settings").hidden, false);
  assert.equal(field.value, "saved.youtube.com");
  assert.equal(submit().body.settings.flowseal_exclude_domains, undefined);
  field.value = "  NEW.GOOGLEVIDEO.COM\r\n\n";
  const update = submit();
  assert.deepEqual(update.body.settings.flowseal_exclude_domains, ["new.googlevideo.com"]);
  assert.equal(update.body.expected, "initial");
  browser.evaluate(`latest.can_edit_flowseal_exclusions = false; controls();`);
  assert.equal(field.readOnly, true);
  assert.match(browser.element("flowseal-exclusion-hint").textContent, /Только чтение/);
  assert.equal(submit().body.settings.flowseal_exclude_domains, undefined);
  browser.evaluate(`latest.can_edit_flowseal_exclusions = true; controls();`);
  field.value = "";
  assert.deepEqual(submit().body.settings.flowseal_exclude_domains, []);
  browser.evaluate(`delete latest.flowseal_exclude_domains; openSettings();`);
  assert.equal(browser.element("flowseal-exclusion-settings").hidden, true);
  assert.equal(submit().body.settings.flowseal_exclude_domains, undefined);
});

test("queue loss fields preserve zero and clear absent or stale observations", () => {
  const browser = page();
  browser.evaluate(
    "renderCounters({queue_dropped: 7, queue_overflow: 7, queue_netlink_dropped: 0})",
  );
  assert.equal(browser.element("queue-dropped").textContent, "7");
  assert.equal(browser.element("queue-overflow").textContent, "7");
  assert.equal(browser.element("queue-netlink-dropped").textContent, "0");
  browser.evaluate("unavailable('offline')");
  for (const name of ["queue-dropped", "queue-overflow", "queue-netlink-dropped"]) {
    assert.equal(browser.element(name).textContent, "Нет данных");
  }
  browser.evaluate("renderCounters({queue_dropped: 0})"); // legacy backend
  assert.equal(browser.element("queue-dropped").textContent, "0");
  assert.equal(browser.element("queue-overflow").textContent, "Нет данных");
});

test("queue drop journal spells out the two deltas and their generation", () => {
  const browser = page();
  browser.evaluate(`renderJournal({available: true, epoch: "trial", omitted: 0, events: [{
    phase: "queue_drops", at: 1000, unit: "xgw-nfqws2.service", generation: 12,
    queue: 201, overflow_delta: 3, netlink_delta: 0
  }]})`);
  const [item] = browser.element("event-list").children;
  const description = item.children[1].textContent;
  assert.match(description, /поколение 12/);
  assert.match(description, /переполнение \+3/);
  assert.match(description, /доставка netlink \+0/);
});

test("worker fault journal distinguishes an IP list failure", () => {
  const browser = page();
  browser.evaluate(`renderJournal({available: true, epoch: "trial", omitted: 0, events: [{
    phase: "worker_fault", at: 1000, unit: "xgw-nfqws2.service", generation: 9,
    queue: 201, reason: "ipset_reload_failed"
  }]})`);
  const [item] = browser.element("event-list").children;
  assert.match(item.children[1].textContent, /поколение 9.*Ошибка загрузки списка IP-адресов/);
});

test("online bypasses backoff and coalesces with an in-flight GET", async () => {
  const browser = page();
  browser.requests[0](503);
  await settle();
  assert.deepEqual(browser.delays(), [8000]);
  browser.emit("online");
  assert.equal(browser.requests.length, 2);
  assert.deepEqual(browser.delays(), [5000]);

  browser.emit("online");
  browser.emit("online");
  assert.equal(browser.requests.length, 2);
  browser.requests[1](503);
  await settle();
  assert.deepEqual(browser.delays(), [0]);
  browser.runTimer(0);
  browser.requests[2](200);
  await settle();
  assert.equal(browser.requests.length, 3);
  assert.deepEqual(browser.delays(), [4000]);
});

test("online leaves a hidden or unauthenticated page idle", async () => {
  const browser = page();
  browser.requests[0](503);
  await settle();
  browser.visibility(true);
  browser.emit("online");
  assert.equal(browser.requests.length, 1);
  assert.deepEqual(browser.delays(), []);

  browser.visibility(false);
  assert.equal(browser.requests.length, 2);
  browser.requests[1](401);
  await settle();
  browser.emit("online");
  assert.equal(browser.requests.length, 2);
  assert.deepEqual(browser.delays(), []);
});

test("retry is offered after a read failure and never starts overlapping requests", async () => {
  const browser = page();
  assert.equal(browser.button.hidden, true);
  browser.requests[0](503);
  await settle();
  assert.equal(browser.button.hidden, false);
  assert.equal(browser.button.disabled, false);
  assert.deepEqual(browser.delays(), [8000]);
  browser.emit("click");
  browser.emit("click");
  assert.equal(browser.button.disabled, true);
  assert.equal(browser.requests.length, 2);
  browser.requests[1](200);
  await settle();
  assert.equal(browser.button.hidden, true);
  assert.deepEqual(browser.delays(), [4000]);
});

test("expired login hides retry and stops polling", async () => {
  const browser = page();
  browser.requests[0](503);
  await settle();
  browser.emit("click");
  browser.requests[1](401);
  await settle();
  assert.equal(browser.button.hidden, true);
  browser.emit("click");
  assert.equal(browser.requests.length, 2);
  assert.deepEqual(browser.delays(), []);
});
