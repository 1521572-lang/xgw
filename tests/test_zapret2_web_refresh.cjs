"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

const source = fs.readFileSync(path.join(__dirname, "../src/xgw/ui/zapret2.js"), "utf8");

function page() {
  const listeners = new Map();
  const element = {
    addEventListener() {},
    querySelector() { return this; },
  };
  const document = {
    hidden: false,
    documentElement: {dataset: {}},
    getElementById: () => element,
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
  vm.runInContext("render = () => { online = true; }; unavailable = () => { online = false; };",
    context);
  return {
    requests,
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
