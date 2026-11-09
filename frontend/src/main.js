import "./styles.css";
import { fetchConfig, fetchHealth, fetchSchemes, postChat } from "./api.js";
import { detectPiiHint } from "./pii.js";

const FOOTER_PREFIX = "Last updated from sources:";

const state = {
  config: null,
  schemes: [],
  sending: false,
  selectedScheme: "",
  health: null,
};

const app = document.getElementById("app");

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

function splitAnswer(text) {
  const marker = `\n${FOOTER_PREFIX}`;
  const index = text.indexOf(marker);
  if (index === -1) {
    return { body: text.trim(), footer: null };
  }
  return {
    body: text.slice(0, index).trim(),
    footer: text.slice(index + 1).trim(),
  };
}

function messageClass(response) {
  if (response?.reason === "needs_clarification") return "assistant clarification";
  if (response?.refusal || response?.reason === "pii_blocked") return "assistant refusal";
  if (response?.reason === "not_found") return "assistant";
  return "assistant";
}

function renderMessage(node, role, text, response = null) {
  node.className = `message ${role}`;
  node.replaceChildren();

  const body = el("div", "message-body");
  if (role === "assistant" && response) {
    const { body: answerBody, footer } = splitAnswer(text);
    body.textContent = answerBody;
    node.appendChild(body);

    if (footer) {
      node.appendChild(el("div", "message-footer", footer));
    } else if (response.last_updated_date) {
      node.appendChild(
        el("div", "message-footer", `${FOOTER_PREFIX} ${response.last_updated_date}`)
      );
    }

    if (response.citation_url) {
      const link = el("a", "citation-link");
      link.href = response.citation_url;
      link.target = "_blank";
      link.rel = "noopener noreferrer";
      link.textContent = "View source";
      node.appendChild(link);
    }
  } else {
    body.textContent = text;
    node.appendChild(body);
  }
}

function setSending(sending) {
  state.sending = sending;
  const sendBtn = document.getElementById("send-btn");
  const input = document.getElementById("chat-input");
  const examples = document.querySelectorAll(".example-btn");
  if (sendBtn) sendBtn.disabled = sending;
  if (input) input.disabled = sending;
  examples.forEach((btn) => {
    btn.disabled = sending;
  });
}

function appendUserMessage(text) {
  const list = document.getElementById("messages");
  const empty = document.getElementById("empty-state");
  if (empty) empty.remove();
  const node = el("div");
  renderMessage(node, "user", text);
  list.appendChild(node);
  list.scrollTop = list.scrollHeight;
}

function appendAssistantMessage(response) {
  const list = document.getElementById("messages");
  const node = el("div");
  renderMessage(node, messageClass(response), response.answer_text, response);
  list.appendChild(node);
  list.scrollTop = list.scrollHeight;
}

function appendErrorMessage(text) {
  const list = document.getElementById("messages");
  const empty = document.getElementById("empty-state");
  if (empty) empty.remove();
  const node = el("div");
  renderMessage(node, "error", text);
  list.appendChild(node);
  list.scrollTop = list.scrollHeight;
}

function updatePiiWarning(text) {
  const warning = document.getElementById("pii-warning");
  const kind = detectPiiHint(text);
  if (!warning) return;
  if (kind) {
    warning.textContent = `Please do not share personal information (${kind}).`;
  } else {
    warning.textContent = "";
  }
}

async function sendMessage(rawText) {
  const text = rawText.trim();
  if (!text || state.sending) return;

  if (detectPiiHint(text)) {
    appendUserMessage(text);
    appendAssistantMessage({
      answer_text:
        "Please do not share personal information such as PAN, Aadhaar, bank account numbers, OTPs, email addresses, or phone numbers.",
      citation_url: null,
      last_updated_date: null,
      refusal: true,
      reason: "pii_blocked",
    });
    return;
  }

  setSending(true);
  appendUserMessage(text);

  try {
    const response = await postChat(text, state.selectedScheme || null);
    appendAssistantMessage(response);
  } catch (error) {
    appendErrorMessage(error.message || "Unable to reach the assistant right now.");
  } finally {
    setSending(false);
  }
}

function buildShell() {
  app.replaceChildren();
  const shell = el("div", "app-shell");

  const hero = el("section", "hero");
  hero.appendChild(el("div", "eyebrow", "HDFC Mutual Funds"));
  hero.appendChild(el("h1", null, "Mutual Fund FAQ Assistant"));
  hero.appendChild(el("p", null, state.config?.welcome_message || "Loading…"));
  hero.appendChild(el("div", "disclaimer", state.config?.disclaimer || "Facts-only. No investment advice."));
  const examples = el("div", "examples");
  examples.id = "examples";
  hero.appendChild(examples);
  shell.appendChild(hero);

  const controls = el("section", "controls panel");
  const label = el("label", null, "Optional scheme (helps for questions like “expense ratio?”)");
  label.htmlFor = "scheme-select";
  controls.appendChild(label);
  const select = el("select");
  select.id = "scheme-select";
  select.appendChild(el("option", null, "Auto-detect scheme from your question"));
  state.schemes.forEach((scheme) => {
    const option = el("option", null, scheme.scheme_name);
    option.value = scheme.id;
    select.appendChild(option);
  });
  select.addEventListener("change", (event) => {
    state.selectedScheme = event.target.value;
  });
  controls.appendChild(select);
  shell.appendChild(controls);

  const panel = el("section", "panel");
  const header = el("div", "chat-header");
  header.appendChild(el("h2", null, "Chat"));
  const status = el("div", "status-pill");
  status.id = "status-pill";
  header.appendChild(status);
  panel.appendChild(header);

  const messages = el("div", "messages");
  messages.id = "messages";
  const empty = el("div", "empty-state");
  empty.id = "empty-state";
  empty.textContent = "Ask a factual question about one of the 10 locked HDFC schemes.";
  messages.appendChild(empty);
  panel.appendChild(messages);
  shell.appendChild(panel);

  const composer = el("section", "composer");
  const textarea = el("textarea");
  textarea.id = "chat-input";
  textarea.placeholder = "e.g. Min SIP for HDFC Small Cap Fund Direct Growth";
  textarea.addEventListener("input", (event) => updatePiiWarning(event.target.value));
  composer.appendChild(textarea);

  const actions = el("div", "composer-actions");
  const left = el("div");
  left.appendChild(el("div", "pii-warning"));
  left.lastChild.id = "pii-warning";
  left.appendChild(
    el("div", "privacy-note", "Do not enter PAN, Aadhaar, OTP, email, or phone numbers.")
  );
  actions.appendChild(left);

  const sendBtn = el("button", "send-btn", "Send");
  sendBtn.id = "send-btn";
  sendBtn.type = "button";
  sendBtn.addEventListener("click", () => {
    const value = textarea.value;
    textarea.value = "";
    updatePiiWarning("");
    sendMessage(value);
  });
  actions.appendChild(sendBtn);
  composer.appendChild(actions);
  shell.appendChild(composer);

  app.appendChild(shell);
  renderExamples();
  updateHealthStatus();
}

function renderExamples() {
  const container = document.getElementById("examples");
  if (!container || !state.config) return;
  container.replaceChildren();
  state.config.example_questions.forEach((question) => {
    const btn = el("button", "example-btn", question);
    btn.type = "button";
    btn.addEventListener("click", () => sendMessage(question));
    container.appendChild(btn);
  });
}

function updateHealthStatus() {
  const pill = document.getElementById("status-pill");
  if (!pill) return;
  if (!state.health) {
    pill.textContent = "Checking index…";
    return;
  }
  if (state.health.index_ready) {
    pill.textContent = `Index ready · ${state.health.scheme_count} schemes`;
    pill.className = "status-pill ready";
  } else {
    pill.textContent = "Index unavailable";
    pill.className = "status-pill degraded";
  }
}

async function init() {
  try {
    const [config, schemes, health] = await Promise.all([
      fetchConfig(),
      fetchSchemes(),
      fetchHealth(),
    ]);
    state.config = config;
    state.schemes = schemes.schemes;
    state.health = health;
  } catch (error) {
    state.config = {
      welcome_message: "Ask factual questions about the 10 locked HDFC mutual fund schemes.",
      disclaimer: "Facts-only. No investment advice.",
      example_questions: [],
    };
    state.schemes = [];
    state.health = { index_ready: false };
    console.error(error);
  }

  buildShell();

  const input = document.getElementById("chat-input");
  input?.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      const value = input.value;
      input.value = "";
      updatePiiWarning("");
      sendMessage(value);
    }
  });
}

init();
