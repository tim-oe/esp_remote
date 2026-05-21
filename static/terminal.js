(function () {
  const statusEl = document.getElementById("status");
  const logoutBtn = document.getElementById("logout-btn");
  const term = new Terminal({
    cursorBlink: true,
    fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace",
    fontSize: 14,
    theme: { background: "#0d1117", foreground: "#e6edf3", cursor: "#58a6ff" },
  });
  const fitAddon = new FitAddon.FitAddon();
  term.loadAddon(fitAddon);
  term.open(document.getElementById("terminal"));
  fitAddon.fit();
  window.addEventListener("resize", () => fitAddon.fit());

  const POLL_MS = 40;
  const STATUS_EVERY = 50;
  const BACKLOG_MS = 15;
  const INPUT_COALESCE_MS = 6;
  let since = 0;
  let pollCount = 0;
  let pollInFlight = false;
  let inputSending = false;
  let inputPending = "";
  let inputCoalesceTimer = null;
  let backlogTimer = null;
  let pollTimer = null;
  let wokeSerial = false;
  let loggingOut = false;

  function setStatus(text, ok) {
    statusEl.textContent = text;
    statusEl.classList.toggle("ok", !!ok);
  }

  function scheduleBacklogPoll() {
    if (backlogTimer !== null) {
      return;
    }
    backlogTimer = setTimeout(function () {
      backlogTimer = null;
      void pollOutput();
    }, BACKLOG_MS);
  }

  async function fetchStatus() {
    const res = await fetch("/api/status", { credentials: "same-origin" });
    if (res.status === 401) {
      window.location.href = "/login.html";
      return null;
    }
    if (!res.ok) {
      return null;
    }
    return res.json();
  }

  async function postInput(batch) {
    const res = await fetch("/api/input", {
      method: "POST",
      credentials: "same-origin",
      body: batch,
    });
    if (res.status === 401) {
      window.location.href = "/login.html";
      return false;
    }
    if (!res.ok) {
      setStatus("send error " + res.status, false);
      return false;
    }
    return true;
  }

  async function flushInput() {
    if (inputSending) {
      return;
    }
    const batch = inputPending;
    if (!batch) {
      return;
    }
    inputPending = "";
    inputSending = true;
    try {
      const ok = await postInput(batch);
      if (!ok) {
        return;
      }
    } catch (err) {
      setStatus("send error", false);
    } finally {
      inputSending = false;
      if (inputPending) {
        void flushInput();
      }
    }
  }

  function scheduleInputFlush() {
    if (inputCoalesceTimer !== null) {
      clearTimeout(inputCoalesceTimer);
    }
    inputCoalesceTimer = setTimeout(function () {
      inputCoalesceTimer = null;
      void flushInput();
    }, INPUT_COALESCE_MS);
  }

  function queueInput(data) {
    inputPending += data;
    if (!inputSending) {
      void flushInput();
    } else {
      scheduleInputFlush();
    }
  }

  async function doLogout() {
    if (loggingOut) {
      return;
    }
    loggingOut = true;
    if (pollTimer !== null) {
      clearInterval(pollTimer);
      pollTimer = null;
    }
    setStatus("logging out…", false);
    try {
      await fetch("/api/input", {
        method: "POST",
        credentials: "same-origin",
        body: "\r\nexit\r\n",
      });
      await fetch("/logout", {
        method: "POST",
        credentials: "same-origin",
        headers: { Accept: "application/json" },
      });
    } catch (err) {
      /* still leave the app */
    }
    window.location.href = "/login.html";
  }

  async function pollOutput() {
    if (loggingOut || pollInFlight) {
      return;
    }
    pollInFlight = true;
    let morePending = false;
    try {
      const res = await fetch("/api/output?since=" + since, {
        credentials: "same-origin",
      });
      if (res.status === 401) {
        window.location.href = "/login.html";
        return;
      }
      if (!res.ok) {
        setStatus("poll error " + res.status, false);
        return;
      }
      const json = await res.json();
      if (json.data) {
        term.write(json.data);
      }
      since = json.since;
      morePending = (json.pending || 0) > 0;

      pollCount += 1;
      if (pollCount % STATUS_EVERY === 0) {
        const st = await fetchStatus();
        if (st) {
          setStatus("rx " + st.rx_total + " B, tx " + st.tx_total + " B", true);
          if (st.rx_total > since) {
            morePending = true;
          }
        } else {
          setStatus("connected", true);
        }
      }
    } catch (err) {
      setStatus("error", false);
    } finally {
      pollInFlight = false;
      if (morePending) {
        scheduleBacklogPoll();
      }
    }
  }

  term.onData(function (data) {
    if (loggingOut) {
      return;
    }
    queueInput(data);
  });

  if (logoutBtn) {
    logoutBtn.addEventListener("click", function () {
      void doLogout();
    });
  }

  async function start() {
    const st = await fetchStatus();
    if (st && st.rx_total > 0) {
      since = st.rx_total;
    }
    void pollOutput();
    pollTimer = setInterval(function () {
      void pollOutput();
    }, POLL_MS);
    setTimeout(function () {
      if (!wokeSerial) {
        wokeSerial = true;
        queueInput("\r\n");
      }
    }, 300);
    term.focus();
  }

  void start();
})();
