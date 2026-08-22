"use strict";

const state = {
  query: "",
  offset: 0,
  sortBy: "date",
  sortDirection: "descending",
  selected: null,
  selectionRequest: null,
  view: null,
  dragExports: new Map(),
  previewUrl: null,
};

const elements = {};
const byId = id => document.getElementById(id);
let initialized = false;

window.addEventListener("pywebviewready", initialize);
window.setTimeout(() => {
  if (window.pywebview?.api?.status) initialize();
  else if (!initialized) showBridgeFailure();
}, 1500);

async function initialize() {
  if (initialized) return;
  initialized = true;
  for (const id of ["choose-archive", "search-form", "search", "archive-label", "result-status", "result-list", "load-more",
    "sort-by", "sort-direction", "message-content", "message-file-well", "message-file-name", "message-subject", "message-headers", "part-select", "remote-content",
    "save-message", "print-message", "body-view", "attachment-section", "attachment-list", "attachment-preview", "error"]) {
    elements[id] = byId(id);
  }
  elements["choose-archive"].addEventListener("click", chooseArchive);
  elements["search-form"].addEventListener("submit", event => { event.preventDefault(); runSearch(false); });
  elements["load-more"].addEventListener("click", () => runSearch(true));
  elements["sort-by"].addEventListener("change", () => runSearch(false));
  elements["sort-direction"].addEventListener("click", toggleSortDirection);
  elements["result-list"].addEventListener("keydown", navigateResults);
  elements["part-select"].addEventListener("change", () => showPart(Number(elements["part-select"].value), false));
  elements["remote-content"].addEventListener("click", () => showPart(Number(elements["part-select"].value), true));
  elements["save-message"].addEventListener("click", () => call(() => window.pywebview.api.save_message(state.selected)));
  elements["print-message"].addEventListener("click", () => window.print());
  installDrag(elements["message-file-well"], () => state.selected);
  document.addEventListener("keydown", handleCommandShortcut);

  const parameters = new URLSearchParams(window.location.search);
  if (parameters.get("standalone") === "1") document.body.classList.add("standalone");
  const status = await call(() => window.pywebview.api.status());
  if (!status) return;
  applyStatus(status);
  const message = Number(parameters.get("message"));
  if (message) await selectMessage(message);
  else if (status.ready) await runSearch(false);
}

function showBridgeFailure() {
  const error = byId("error");
  error.textContent = "The native application bridge did not start. Restart mailsearch-gui and check its terminal output.";
  error.hidden = false;
}

async function chooseArchive() {
  const status = await call(() => window.pywebview.api.choose_archive());
  if (status) { applyStatus(status); if (status.ready) await runSearch(false); }
}

function applyStatus(status) {
  elements["archive-label"].textContent = status.archive || "No archive selected";
  elements.search.disabled = !status.ready;
  elements["result-status"].textContent = status.ready ? "Enter a search or press Return for newest mail." : "Choose an archive to begin.";
  if (status.ready) elements.search.focus();
}

async function runSearch(append) {
  const query = elements.search.value.trim();
  const sortBy = elements["sort-by"].value;
  const sortDirection = state.sortDirection;
  const sameSearch = query === state.query && sortBy === state.sortBy && sortDirection === state.sortDirection;
  const offset = append && sameSearch ? state.offset : 0;
  elements["result-status"].textContent = "Searching…";
  const page = await call(() => window.pywebview.api.search(query, offset, sortBy, sortDirection));
  if (!page) return;
  state.query = query;
  state.sortBy = sortBy;
  state.sortDirection = sortDirection;
  state.offset = offset + page.results.length;
  if (!append) elements["result-list"].replaceChildren();
  for (const result of page.results) {
    const row = resultRow(result);
    elements["result-list"].append(row);
  }
  requestPreviews(page.results.map(result => result.message_pk));
  elements["result-status"].textContent = `${state.offset.toLocaleString()} message${state.offset === 1 ? "" : "s"}${page.has_more ? " shown" : ""}`;
  elements["load-more"].hidden = !page.has_more;
}

function toggleSortDirection() {
  state.sortDirection = state.sortDirection === "descending" ? "ascending" : "descending";
  const descending = state.sortDirection === "descending";
  elements["sort-direction"].textContent = descending ? "↓" : "↑";
  elements["sort-direction"].ariaLabel = descending ? "Sort descending" : "Sort ascending";
  elements["sort-direction"].title = elements["sort-direction"].ariaLabel;
  runSearch(false);
}

function resultRow(result) {
  const row = document.createElement("div");
  row.className = "result";
  row.id = `message-result-${result.message_pk}`;
  row.setAttribute("role", "option");
  row.setAttribute("aria-selected", "false");
  row.dataset.messagePk = result.message_pk;
  row.draggable = true;
  const subjectLine = document.createElement("div");
  subjectLine.className = "result-subject-line";
  const subject = document.createElement("div");
  subject.className = "result-subject";
  subject.textContent = result.subject || "(no subject)";
  const paperclip = document.createElement("span");
  paperclip.className = "result-attachment";
  paperclip.textContent = result.attachment_count > 1 ? `📎 ${result.attachment_count}` : "📎";
  paperclip.title = `${result.attachment_count} attachment${result.attachment_count === 1 ? "" : "s"}`;
  paperclip.setAttribute("aria-label", paperclip.title);
  paperclip.hidden = result.attachment_count === 0;
  subjectLine.append(subject, paperclip);
  const line = document.createElement("div");
  line.className = "result-line";
  const sender = document.createElement("span");
  sender.className = "result-sender";
  sender.textContent = result.sender || "(missing sender)";
  const date = document.createElement("span");
  date.className = "result-date";
  date.textContent = formatDate(result.date_utc);
  line.append(sender, date);
  const preview = document.createElement("div");
  preview.className = "result-preview";
  preview.setAttribute("aria-label", "Message preview");
  row.append(subjectLine, line, preview);
  row.addEventListener("mousedown", () => elements["result-list"].focus({preventScroll: true}));
  row.addEventListener("click", () => selectMessage(result.message_pk));
  row.addEventListener("dblclick", () => call(() => window.pywebview.api.open_message_window(result.message_pk)));
  installDrag(row, () => result.message_pk);
  return row;
}

async function requestPreviews(messagePks) {
  if (!messagePks.length) return;
  const requested = await call(() => window.pywebview.api.request_previews(messagePks));
  if (requested === null) return;
  while (true) {
    const batch = await call(() => window.pywebview.api.take_previews(messagePks));
    if (!batch) return;
    for (const item of batch.previews) {
      const preview = document.querySelector(`.result[data-message-pk="${item.message_pk}"] .result-preview`);
      if (preview) preview.textContent = item.preview;
    }
    if (batch.error) { showError(`Could not load message previews: ${batch.error}`); return; }
    if (!batch.pending) return;
    await new Promise(resolve => setTimeout(resolve, 75));
  }
}

async function selectMessage(messagePk) {
  state.selectionRequest = messagePk;
  const view = await call(() => window.pywebview.api.message(messagePk));
  if (!view || state.selectionRequest !== messagePk) return;
  state.selected = messagePk;
  state.view = view;
  document.querySelectorAll(".result.selected").forEach(row => {
    row.classList.remove("selected");
    row.setAttribute("aria-selected", "false");
  });
  const selectedRow = document.querySelector(`.result[data-message-pk="${messagePk}"]`);
  selectedRow?.classList.add("selected");
  selectedRow?.setAttribute("aria-selected", "true");
  elements["result-list"].setAttribute("aria-activedescendant", `message-result-${messagePk}`);
  elements["message-content"].hidden = false;
  elements["message-subject"].textContent = view.subject;
  elements["message-file-name"].textContent = state.dragExports.get(messagePk)?.filename || "Message.eml";
  elements["message-headers"].replaceChildren(...headerNodes(view.headers));
  elements["part-select"].replaceChildren(...view.body_parts.map(partOption));
  elements["part-select"].value = String(view.preferred_part_id);
  renderAttachments(view.attachments);
  await showPart(view.preferred_part_id, false);
  prepareDrag(messagePk);
}

function navigateResults(event) {
  if (!['ArrowUp', 'ArrowDown'].includes(event.key)) return;
  const rows = [...elements["result-list"].querySelectorAll(".result")];
  if (!rows.length) return;
  event.preventDefault();
  let index = rows.findIndex(row => Number(row.dataset.messagePk) === state.selected);
  if (event.key === "ArrowDown") index = Math.min(index + 1, rows.length - 1);
  else index = index < 0 ? rows.length - 1 : Math.max(index - 1, 0);
  const row = rows[index];
  row.scrollIntoView({block: "nearest"});
  selectMessage(Number(row.dataset.messagePk));
}

function handleCommandShortcut(event) {
  if (!event.metaKey || event.altKey || !state.view) return;
  let partId = null;
  if (event.key === "0" || (event.shiftKey && event.key.toLowerCase() === "u")) partId = -1;
  else if (!event.shiftKey && /^[1-9]$/.test(event.key)) partId = Number(event.key);
  if (partId === null) return;
  event.preventDefault();
  const part = state.view.body_parts.find(candidate => candidate.part_id === partId);
  if (!part) { showError(`This message has no displayable MIME part ${partId}.`); return; }
  elements["part-select"].value = String(partId);
  showPart(partId, false);
}

function headerNodes(headers) {
  const important = new Set(["from", "to", "cc", "subject", "date"]);
  return headers.filter(header => important.has(header.name.toLowerCase())).flatMap(header => {
    const term = document.createElement("dt"); term.textContent = `${header.name}:`;
    const value = document.createElement("dd"); value.textContent = header.value;
    return [term, value];
  });
}

function partOption(part) {
  const option = document.createElement("option");
  option.value = part.part_id;
  option.textContent = part.label;
  return option;
}

async function showPart(partId, allowRemote) {
  if (!state.selected) return;
  const part = await call(() => window.pywebview.api.part(state.selected, partId, allowRemote));
  if (!part) return;
  elements["body-view"].replaceChildren();
  elements["remote-content"].hidden = !part.remote_content_blocked;
  if (part.kind === "html") {
    const frame = document.createElement("iframe");
    frame.className = "html-frame";
    frame.setAttribute("sandbox", "allow-popups");
    frame.srcdoc = part.content;
    frame.addEventListener("load", () => resizeFrame(frame));
    elements["body-view"].append(frame);
  } else {
    const body = document.createElement("div");
    body.className = part.kind === "raw" ? "raw" : "plain";
    body.textContent = part.content;
    elements["body-view"].append(body);
  }
}

function resizeFrame(frame) {
  try { frame.style.height = `${Math.max(460, frame.contentDocument.documentElement.scrollHeight + 20)}px`; } catch (_) { /* sandbox */ }
}

function renderAttachments(attachments) {
  elements["attachment-section"].hidden = attachments.length === 0;
  elements["attachment-list"].replaceChildren();
  clearAttachmentPreview();
  for (const attachment of attachments) {
    const item = document.createElement("div");
    item.className = "attachment";
    const name = document.createElement("span"); name.className = "attachment-name"; name.textContent = attachment.filename;
    const size = document.createElement("span"); size.className = "attachment-size"; size.textContent = byteSize(attachment.byte_length);
    item.append(name, size);
    if (attachment.preview) item.append(actionButton("Preview", () => previewAttachment(attachment)));
    item.append(actionButton("Open", () => openAttachment(attachment)));
    item.append(actionButton("Save…", () => saveAttachment(attachment)));
    elements["attachment-list"].append(item);
  }
}

function actionButton(label, action) {
  const button = document.createElement("button");
  button.type = "button";
  button.textContent = label;
  button.addEventListener("click", action);
  return button;
}

async function previewAttachment(attachment) {
  const content = await call(() => window.pywebview.api.attachment(state.selected, attachment.part_id));
  if (!content) return;
  clearAttachmentPreview();
  const bytes = Uint8Array.from(atob(content.content_base64), character => character.charCodeAt(0));
  state.previewUrl = URL.createObjectURL(new Blob([bytes], {type: content.content_type}));
  const preview = attachment.preview === "image" ? document.createElement("img") : document.createElement("iframe");
  preview.src = state.previewUrl;
  preview.alt = content.filename;
  elements["attachment-preview"].append(preview);
}

async function openAttachment(attachment) {
  let result = await call(() => window.pywebview.api.open_attachment(state.selected, attachment.part_id, false));
  if (result?.requires_confirmation && confirm(`${attachment.filename} may contain executable content. Open it anyway?`)) {
    result = await call(() => window.pywebview.api.open_attachment(state.selected, attachment.part_id, true));
  }
}

function saveAttachment(attachment) {
  call(() => window.pywebview.api.save_attachment(state.selected, attachment.part_id));
}

function clearAttachmentPreview() {
  if (state.previewUrl) URL.revokeObjectURL(state.previewUrl);
  state.previewUrl = null;
  elements["attachment-preview"].replaceChildren();
}

function installDrag(element, messagePk) {
  element.addEventListener("pointerenter", () => prepareDrag(messagePk()));
  element.addEventListener("dragstart", event => {
    const info = state.dragExports.get(messagePk());
    if (!info) { event.preventDefault(); showError("Message export is still being prepared; drag again."); return; }
    event.dataTransfer.effectAllowed = "copy";
    event.dataTransfer.setData("text/uri-list", info.url);
    event.dataTransfer.setData("DownloadURL", `message/rfc822:${info.filename}:${info.url}`);
    event.dataTransfer.setData("text/plain", info.url);
  });
}

async function prepareDrag(messagePk) {
  if (!messagePk || state.dragExports.has(messagePk)) return;
  const info = await call(() => window.pywebview.api.prepare_drag(messagePk));
  if (info) {
    state.dragExports.set(messagePk, info);
    if (state.selected === messagePk) elements["message-file-name"].textContent = info.filename;
  }
}

async function call(operation) {
  try { return await operation(); }
  catch (error) { showError(String(error?.message || error)); return null; }
}

function showError(message) {
  elements.error.textContent = message;
  elements.error.hidden = false;
  clearTimeout(showError.timer);
  showError.timer = setTimeout(() => { elements.error.hidden = true; }, 6000);
}

function formatDate(value) {
  const date = new Date(value);
  return Number.isNaN(date.valueOf()) ? value : new Intl.DateTimeFormat(undefined, {dateStyle: "medium"}).format(date);
}

function byteSize(value) {
  if (value < 1024) return `${value} B`;
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`;
  return `${(value / 1024 / 1024).toFixed(1)} MB`;
}
