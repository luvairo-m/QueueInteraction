import { getExample, submitJob, waitForResult } from "./jobs.js";

const form = document.querySelector("#csv-form");
const csv = document.querySelector("#csv");
const submit = document.querySelector("#submit");
const example = document.querySelector("#example");
const retry = document.querySelector("#retry");
const inputError = document.querySelector("#input-error");
const jobState = document.querySelector("#job-state");
const badge = document.querySelector("#status-badge");
const statusMessage = document.querySelector("#status-message");
const responseTime = document.querySelector("#response-time");
const jobMeta = document.querySelector("#job-meta");
const jobLink = document.querySelector("#job-link");
const resultDetails = document.querySelector("#result-details");
const columns = document.querySelector("#column-results");
const rowCount = document.querySelector("#row-count");
const duplicateCount = document.querySelector("#duplicate-count");
const missingCount = document.querySelector("#missing-count");
const formatCount = new Intl.NumberFormat("ru-RU").format;

let jobUrl;

const rabbitmqLink = document.querySelector("#rabbitmq-link");
const rabbitmqUrl = new URL(rabbitmqLink.href);
rabbitmqUrl.hostname = location.hostname;
rabbitmqLink.href = rabbitmqUrl.href;

function setBusy(busy, label = "Проверить CSV") {
  for (const button of [submit, example, retry]) button.disabled = busy;
  csv.readOnly = busy;
  submit.textContent = label;
}

function showState(state, label, message) {
  jobState.dataset.state = state;
  badge.textContent = label;
  statusMessage.textContent = message;
}

function showInputError(message = "", invalidCsv = false) {
  inputError.textContent = message;
  inputError.hidden = !message;
  csv.setAttribute("aria-invalid", String(invalidCsv));
}

function resetResult() {
  jobUrl = undefined;
  for (const element of [responseTime, jobMeta, resultDetails, retry]) element.hidden = true;
  for (const counter of [rowCount, duplicateCount, missingCount]) counter.textContent = "-";
  columns.replaceChildren();
}

function showAccepted({ id, elapsed }) {
  jobUrl = `/jobs/${encodeURIComponent(id)}`;
  jobLink.href = jobUrl;
  jobLink.textContent = id;
  jobMeta.hidden = false;
  responseTime.textContent = `HTTP 202 · ${formatCount(elapsed)} мс`;
  responseTime.hidden = false;
}

function columnRow(column, missing) {
  const row = document.createElement("tr");
  const name = document.createElement("th");
  name.scope = "row";
  name.textContent = column;
  row.append(name);
  row.insertCell().textContent = formatCount(missing);
  return row;
}

function showResult(result) {
  rowCount.textContent = formatCount(result.rows);
  duplicateCount.textContent = formatCount(result.duplicateRows);
  let totalMissing = 0;
  const rows = document.createDocumentFragment();

  for (const [column, missing] of Object.entries(result.missingByColumn)) {
    rows.append(columnRow(column, missing));
    totalMissing += missing;
  }

  missingCount.textContent = formatCount(totalMissing);
  columns.replaceChildren(rows);
  resultDetails.hidden = false;
  showState("done", "DONE", "Проверка завершена. Результат получен из очереди results.");
}

async function pollResult() {
  retry.hidden = true;
  showState("accepted", "ACCEPTED", "Задача в очереди или уже обрабатывается.");
  try {
    showResult(await waitForResult(jobUrl));
  } catch (error) {
    if (error.status === 404) {
      showState("error", "Нет задачи", "Задача больше недоступна. Отправьте CSV повторно.");
      return;
    }
    showState("error", "Ожидание прервано", "Результат пока недоступен. Проверьте статус задачи ещё раз.");
    retry.hidden = false;
  }
}

async function loadExample() {
  showInputError();
  setBusy(true);
  try {
    csv.value = await getExample();
    csv.focus();
  } catch {
    showInputError("Пример не загрузился. Попробуйте ещё раз или вставьте свой CSV.");
  } finally {
    setBusy(false);
  }
}

async function submitCsv(event) {
  event.preventDefault();
  if (submit.disabled) return;
  if (!csv.value.trim()) {
    showInputError("Вставьте CSV или подставьте пример.", true);
    csv.focus();
    return;
  }

  showInputError();
  resetResult();
  setBusy(true, "Отправляем…");
  showState("sending", "Отправка", "Ожидаем подтверждения от API.");

  try {
    showAccepted(await submitJob(csv.value));
    setBusy(true, "Проверяем…");
    await pollResult();
  } catch (error) {
    if (error.status === 422) {
      showInputError("Проверьте заголовки, кавычки и число полей в каждой строке CSV.", true);
      showState("idle", "Ожидание", "Исправьте CSV и отправьте его снова.");
      csv.focus();
      return;
    }
    showInputError("API не подтвердил приём задачи. Попробуйте ещё раз.");
    showState("error", "Сбой отправки", "Подтверждение не получено.");
  } finally {
    setBusy(false);
  }
}

async function retryPolling() {
  setBusy(true, "Проверяем…");
  try {
    await pollResult();
  } finally {
    setBusy(false);
  }
}

csv.addEventListener("input", () => showInputError());
example.addEventListener("click", loadExample);
form.addEventListener("submit", submitCsv);
retry.addEventListener("click", retryPolling);
