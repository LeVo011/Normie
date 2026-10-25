const textSample = `Students enroll in courses each semester. A student has a name and email.
Each course has a title and is taught by one instructor. An instructor has a name.
For each student, course, and semester, store the final grade.`;

const sqlSample = `CREATE TABLE enrollment_report (
    student_id INTEGER NOT NULL,
    student_name VARCHAR(100) NOT NULL,
    student_email VARCHAR(255) NOT NULL,
    course_id INTEGER NOT NULL,
    course_title VARCHAR(200) NOT NULL,
    instructor_id INTEGER NOT NULL,
    instructor_name VARCHAR(100) NOT NULL,
    semester VARCHAR(20) NOT NULL,
    grade CHAR(2),
    PRIMARY KEY (student_id, course_id, semester)
);`;

const sourceText = document.querySelector("#sourceText");
const normalizeButton = document.querySelector("#normalizeButton");
const status = document.querySelector("#status");
const emptyState = document.querySelector("#emptyState");
const result = document.querySelector("#result");
const connectionStatus = document.querySelector("#connectionStatus");

async function loadServiceStatus() {
  try {
    const response = await fetch("/health");
    const payload = await response.json();
    connectionStatus.textContent = payload.groq_configured
      ? `Groq connected: ${payload.model}`
      : "Demo mode: add GROQ_API_KEY for custom input";
  } catch {
    connectionStatus.textContent = "API status unavailable";
  }
}

loadServiceStatus();

document.querySelector("#loadTextSample").addEventListener("click", () => { sourceText.value = textSample; });
document.querySelector("#loadSqlSample").addEventListener("click", () => { sourceText.value = sqlSample; });

function setStatus(message, error = false) {
  status.textContent = message;
  status.classList.toggle("error", error);
}

function renderSchema(tables) {
  const grid = document.createElement("div");
  grid.className = "schema-grid";
  tables.forEach((table) => {
    const card = document.createElement("article");
    card.className = "table-card";
    const heading = document.createElement("h3");
    heading.textContent = table.name;
    const list = document.createElement("ul");
    list.className = "columns";
    table.columns.forEach((column) => {
      const item = document.createElement("li");
      const flags = [];
      if (table.primary_key.includes(column.name)) flags.push("PK");
      if (table.foreign_keys.some((key) => key.columns.includes(column.name))) flags.push("FK");
      item.textContent = `${column.name} ${column.data_type}`;
      if (flags.length) {
        const tag = document.createElement("span");
        tag.className = "tag";
        tag.textContent = flags.join(", ");
        item.append(tag);
      }
      list.append(item);
    });
    card.append(heading, list);
    grid.append(card);
  });
  const panel = document.querySelector("#schemaPanel");
  panel.replaceChildren(grid);
}

function selectTab(name) {
  document.querySelectorAll("[role=tab]").forEach((tab) => {
    const active = tab.dataset.tab === name;
    tab.setAttribute("aria-selected", String(active));
    document.querySelector(`#${tab.dataset.tab}Panel`).hidden = !active;
  });
}

document.querySelectorAll("[role=tab]").forEach((tab) => {
  tab.addEventListener("click", () => selectTab(tab.dataset.tab));
});

normalizeButton.addEventListener("click", async () => {
  const text = sourceText.value.trim();
  if (!text) {
    setStatus("Add input first", true);
    sourceText.focus();
    return;
  }
  normalizeButton.disabled = true;
  setStatus("Normalizing...");
  try {
    const response = await fetch("/normalize", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        text,
        allow_demo_fallback: true,
        target_normal_form: document.querySelector("input[name=normalForm]:checked").value,
        verify: document.querySelector("#verifySchema").checked,
        max_refinement_attempts: 1,
      }),
    });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.detail || "Normalization request failed.");
    renderSchema(payload.normalization.tables);
    document.querySelector("#sqlPanel").textContent = payload.sql;
    document.querySelector("#reportPanel").textContent = payload.report;
    document.querySelector("#erdPanel").textContent = payload.erd;
    const entity = payload.normalization.entities[0];
    const verifierSummary = payload.verification
      ? ` Verifier: ${payload.verification.approved ? "approved" : "review completed"}. Refinement passes: ${payload.refinement_attempts}.`
      : "";
    document.querySelector("#summary").textContent =
      `${payload.input_kind === "sql_ddl" ? "SQL DDL" : "Natural-language input"} normalized into ` +
      `${payload.normalization.tables.length} relations. Candidate key: (${entity.candidate_keys[0].join(", ")}).${verifierSummary}`;
    emptyState.hidden = true;
    result.hidden = false;
    selectTab("schema");
    setStatus("Complete");
  } catch (error) {
    setStatus(error.message, true);
  } finally {
    normalizeButton.disabled = false;
  }
});
