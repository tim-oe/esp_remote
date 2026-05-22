(function () {
  /* PuTTY-style 16-color palette; xterm.js renders ANSI SGR from the Pi shell. */
  const PUTTY_THEME = {
    background: "#000000",
    foreground: "#c0c0c0",
    cursor: "#00ff00",
    cursorAccent: "#000000",
    selectionBackground: "#0070c1",
    selectionForeground: "#ffffff",
    black: "#000000",
    red: "#bb0000",
    green: "#00bb00",
    yellow: "#bbbb00",
    blue: "#0000bb",
    magenta: "#bb00bb",
    cyan: "#00bbbb",
    white: "#bbbbbb",
    brightBlack: "#555555",
    brightRed: "#ff5555",
    brightGreen: "#55ff55",
    brightYellow: "#ffff55",
    brightBlue: "#5555ff",
    brightMagenta: "#ff55ff",
    brightCyan: "#55ffff",
    brightWhite: "#ffffff",
  };

  const statusEl = document.getElementById("status");
  const logoutBtn = document.getElementById("logout-btn");
  const term = new Terminal({
    cursorBlink: true,
    drawBoldTextInBrightColors: true,
    minimumContrastRatio: 1,
    fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace",
    fontSize: 14,
    theme: PUTTY_THEME,
  });
  const fitAddon = new FitAddon.FitAddon();
  term.loadAddon(fitAddon);
  term.open(document.getElementById("terminal"));
  fitAddon.fit();
  window.addEventListener("resize", () => fitAddon.fit());

  const POLL_MS = 40;
  const STATUS_EVERY = 50;
  const BACKLOG_MS = 15;
  const BACKLOG_URGENT_MS = 0;
  const BACKLOG_URGENT_PENDING = 512;
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

  function scheduleBacklogPoll(urgent) {
    const delay =
      urgent ? BACKLOG_URGENT_MS : BACKLOG_MS;
    if (backlogTimer !== null) {
      if (!urgent) {
        return;
      }
      clearTimeout(backlogTimer);
      backlogTimer = null;
    }
    backlogTimer = setTimeout(function () {
      backlogTimer = null;
      void pollOutput();
    }, delay);
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
      const pendingBytes = json.pending || 0;
      morePending = pendingBytes > 0 || !!json.gap;

      pollCount += 1;
      const statusEvery =
        pendingBytes > BACKLOG_URGENT_PENDING ? 5 : STATUS_EVERY;
      if (pollCount % statusEvery === 0) {
        const st = await fetchStatus();
        if (st) {
          setStatus("rx " + st.rx_total + " B, tx " + st.tx_total + " B", true);
          if (st.rx_total > since || (st.uart_pending || 0) > 0) {
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
        scheduleBacklogPoll(pendingBytes > BACKLOG_URGENT_PENDING);
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
