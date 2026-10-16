"use strict";

const state = { run: null };

const $ = (id) => document.getElementById(id);
const esc = (value) =>
  String(value == null ? "" : value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");

function showStep(n) {
  document.querySelectorAll(".step").forEach((s) => (s.hidden = true));
  $("step-" + n).hidden = false;
  document.querySelectorAll("#step-indicator li").forEach((li) => {
    const step = Number(li.dataset.step);
    li.classList.toggle("active", step === n);
    li.classList.toggle("done", step < n);
  });
  window.scrollTo({ top: 0, behavior: "smooth" });
}

function setLoadStatus(text) {
  const el = $("load-status");
  el.textContent = text;
  el.hidden = !text;
}

function showLoadError(text) {
  const box = $("error-box");
  box.textContent = text;
  box.hidden = !text;
}

function toggleSource() {
  const useUpload = $("src-upload").checked;
  $("csv-file").disabled = !useUpload;
}

async function startRun() {
  showLoadError("");
  setLoadStatus("Running analysis…");
  $("btn-run").disabled = true;

  try {
    let response;
    const file = $("csv-file").files[0];
    if ($("src-upload").checked && file) {
      const form = new FormData();
      form.append("file", file);
      response = await fetch("/api/runs", { method: "POST", body: form });
    } else {
      response = await fetch("/api/runs", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ use_sample: true }),
      });
    }

    const body = await response.json();
    if (!response.ok) {
      throw new Error(body.detail || "Request failed (" + response.status + ")");
    }
    if (body.status === "failed") {
      throw new Error(body.error || "The run failed.");
    }

    state.run = body;
    renderInsights(body);
    setLoadStatus("");
    showStep(2);
  } catch (err) {
    setLoadStatus("");
    showLoadError(err.message);
  } finally {
    $("btn-run").disabled = false;
  }
}

function renderInsights(run) {
  const intel = run.intelligence || {};
  const themes = intel.themes || [];
  const top = intel.top_themes || [];

  $("run-meta").textContent =
    "Run " + run.id + " · status " + run.status;

  $("theme-meta").textContent = "(" + themes.length + " of max 5)";
  $("theme-list").innerHTML =
    themes
      .map((t) => {
        const isTop = top.includes(t.name);
        return (
          '<li class="' + (isTop ? "top" : "") + '">' +
          "<strong>" + esc(t.name) + "</strong>" +
          (isTop ? '<span class="badge">top</span>' : "") +
          "<p>" + esc(t.summary || "") + "</p>" +
          '<small class="muted">' + (t.review_count || 0) + " reviews</small>" +
          "</li>"
        );
      })
      .join("") || '<li class="muted">No themes returned.</li>';

  const quotes = intel.quotes || [];
  $("quote-list").innerHTML =
    quotes
      .map(
        (q) =>
          "<blockquote>" + esc(q.text) +
          '<br><small class="muted">review ' + esc(q.review_id) +
          (q.rating != null ? " · " + esc(q.rating) + "★" : "") +
          (q.date ? " · " + esc(q.date) : "") +
          "</small></blockquote>"
      )
      .join("") || '<p class="muted">No verified quotes.</p>';

  const fee = intel.fee_issue;
  $("fee-card").innerHTML = fee
    ? '<p><strong>' + esc(fee.name) + "</strong></p>" +
      "<p>" + esc(fee.why_confused) + "</p>" +
      "<blockquote>" + esc(fee.evidence_quote) +
      '<br><small class="muted">evidence: review ' + esc(fee.evidence_review_id) +
      "</small></blockquote>"
    : '<div class="fee-empty">No recurring fee issue detected — the explainer is skipped and no fee is invented.</div>';

  const pulse = run.pulse;
  $("pulse-count").textContent = pulse ? pulse.word_count + " words" : "";
  $("pulse-body").textContent = pulse ? pulse.markdown : "No pulse.";

  const explainer = run.explainer;
  $("explainer-count").textContent = explainer
    ? explainer.bullets.length + " bullets"
    : "";
  $("explainer-body").innerHTML = explainer
    ? "<ul class=\"bullets\">" +
      explainer.bullets.map((b) => "<li>" + esc(b) + "</li>").join("") +
      "</ul><p class=\"muted\">Sources: " +
      explainer.source_links.map(esc).join(", ") +
      "<br>Last checked: " + esc(explainer.last_checked || "") + "</p>"
    : '<div class="fee-empty">No fee issue — explainer not generated.</div>';

  $("payload-json").textContent = JSON.stringify(run.payload, null, 2);
  updateDecisionButtons(run);
}

function updateDecisionButtons(run) {
  const ready = run.status === "ready_for_approval";
  const done = run.status === "approved" || run.status === "rejected";
  $("btn-approve").disabled = !ready;
  $("btn-reject").disabled = !ready || done;
}

async function decide(action) {
  if (!state.run) return;
  $("decision-error").hidden = true;
  $("btn-approve").disabled = true;
  $("btn-reject").disabled = true;
  $("decision-status").textContent =
    action === "approve" ? "Approving — writing files…" : "Rejecting…";
  $("decision-status").hidden = false;

  try {
    const response = await fetch(
      "/api/runs/" + state.run.id + "/" + action,
      { method: "POST" }
    );
    const body = await response.json();
    if (!response.ok) {
      throw new Error(body.detail || "Request failed (" + response.status + ")");
    }
    state.run = body;
    renderLogs(body, action);
  } catch (err) {
    $("decision-error").textContent = err.message;
    $("decision-error").hidden = false;
    $("decision-status").hidden = true;
  } finally {
    updateDecisionButtons(state.run);
    $("btn-back-2").disabled = false;
  }
}

function renderArtifacts(run) {
  const written = (run.logs || []).filter((log) => log.ok);
  const names = {
    append_notes: "notes.md",
    create_email_draft: "email-draft.md",
  };
  const items = written
    .filter((log) => names[log.tool])
    .map((log) => {
      const slug = log.tool === "append_notes" ? "notes" : "email-draft";
      const base = "/api/runs/" + encodeURIComponent(run.id) + "/artifacts/" + slug;
      return (
        "<li><strong>" + esc(names[log.tool]) + "</strong>" +
        '<a href="' + base + '" target="_blank" rel="noopener">View</a>' +
        '<a href="' + base + '?download=true">Download</a></li>'
      );
    });

  $("artifact-list").innerHTML =
    items.join("") || '<li class="muted">No files were written.</li>';
  $("artifacts-card").hidden = items.length === 0;
}

function renderLogs(run, action) {
  if (action === "reject") {
    $("decision-status").textContent =
      "Rejected — no files were written. New notes block: none.";
    $("artifacts-card").hidden = true;
  } else if (run.status === "approved") {
    $("decision-status").textContent =
      "Approved — notes and email draft written.";
  } else {
    $("decision-status").textContent =
      "Approve incomplete — see the failed tool below and approve again to retry it.";
  }

  renderArtifacts(run);

  const logs = run.logs || [];
  $("logs-card").hidden = logs.length === 0;
  $("log-rows").innerHTML = logs
    .map(
      (log) =>
        "<tr><td>" + esc(log.tool) + "</td>" +
        '<td class="' + (log.ok ? "ok" : "fail") + '">' +
        (log.ok ? "ok" : "failed") + "</td>" +
        "<td>" + esc(log.error || log.location || "") + "</td></tr>"
    )
    .join("");
}

window.addEventListener("DOMContentLoaded", () => {
  $("src-sample").addEventListener("change", toggleSource);
  $("src-upload").addEventListener("change", toggleSource);
  $("btn-run").addEventListener("click", startRun);
  $("btn-back-1").addEventListener("click", () => showStep(1));
  $("btn-next-3").addEventListener("click", () => showStep(3));
  $("btn-back-2").addEventListener("click", () => showStep(2));
  $("btn-approve").addEventListener("click", () => decide("approve"));
  $("btn-reject").addEventListener("click", () => decide("reject"));
  toggleSource();
});
