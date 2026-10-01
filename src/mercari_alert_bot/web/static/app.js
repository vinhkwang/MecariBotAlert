"use strict";

(function startMercariAlertUi() {
  const ICT_TIME_FORMAT = new Intl.DateTimeFormat("en-GB", {
    timeZone: "Asia/Ho_Chi_Minh",
    dateStyle: "medium",
    timeStyle: "medium",
  });

  const messageElement = document.getElementById("message");
  const keywordRowsElement = document.getElementById("keyword-rows");
  const keywordCreateForm = document.getElementById("keyword-create-form");
  const keywordImportForm = document.getElementById("keyword-import-form");
  const testNotificationButton = document.getElementById("test-notification-button");
  const settingsForm = document.getElementById("settings-form");
  const estimatedLatencyElement = document.getElementById("estimated-latency");

  let keywordRules = [];
  let editingRuleId = null;

  async function requestJson(method, path, body) {
    const options = { method, headers: { Accept: "application/json" } };
    if (body !== undefined) {
      options.headers["Content-Type"] = "application/json";
      options.body = JSON.stringify(body);
    }
    const response = await fetch(path, options);
    if (response.status === 204) {
      return null;
    }
    const payload = await response.json().catch(() => null);
    if (!response.ok) {
      throw new Error(describeErrorDetail(payload, response.status));
    }
    return payload;
  }

  function describeErrorDetail(payload, statusCode) {
    if (payload && typeof payload.detail === "string") {
      return payload.detail;
    }
    if (payload && Array.isArray(payload.detail)) {
      return payload.detail.map((entry) => entry.msg).join("; ");
    }
    return "Request failed with status " + statusCode;
  }

  function showMessage(text, isError) {
    messageElement.textContent = text;
    messageElement.className = isError ? "is-error" : "is-success";
  }

  async function runAction(action, successText) {
    try {
      await action();
      if (successText) {
        showMessage(successText, false);
      }
    } catch (error) {
      showMessage(error.message, true);
    }
  }

  function buildElement(tagName, text) {
    const element = document.createElement(tagName);
    if (text !== undefined) {
      element.textContent = text;
    }
    return element;
  }

  function buildButton(label, onClick, isDangerous) {
    const button = buildElement("button", label);
    button.type = "button";
    if (isDangerous) {
      button.className = "danger";
    }
    button.addEventListener("click", onClick);
    return button;
  }

  function buildCell(...children) {
    const cell = buildElement("td");
    cell.append(...children);
    return cell;
  }

  function formatIctTime(isoText) {
    return isoText ? ICT_TIME_FORMAT.format(new Date(isoText)) : "never";
  }

  function countEnabledRules() {
    return keywordRules.filter((rule) => rule.is_enabled).length;
  }

  function describeBaseline(rule) {
    if (!rule.has_baseline) {
      return "Seeds on next cycle";
    }
    return "Since " + formatIctTime(rule.baseline_established_at);
  }

  function buildEnabledToggle(rule) {
    const checkbox = buildElement("input");
    checkbox.type = "checkbox";
    checkbox.checked = rule.is_enabled;
    checkbox.setAttribute("aria-label", "Enable " + rule.name);
    checkbox.addEventListener("change", () =>
      runAction(async () => {
        await requestJson("PATCH", "/api/keywords/" + rule.id, { is_enabled: checkbox.checked });
        await refreshKeywords();
      }, checkbox.checked ? "Rule enabled" : "Rule disabled"),
    );
    return checkbox;
  }

  function buildDisplayRow(rule) {
    const row = buildElement("tr");
    row.append(
      buildCell(rule.name),
      buildCell(rule.query),
      buildCell(buildEnabledToggle(rule)),
      buildCell(describeBaseline(rule)),
      buildCell(
        buildButton("Edit", () => startEditingRule(rule.id)),
        buildButton("Reset baseline", () => resetRuleBaseline(rule)),
        buildButton("Delete", () => deleteRule(rule), true),
      ),
    );
    return row;
  }

  function buildTextInput(value, label) {
    const input = buildElement("input");
    input.value = value;
    input.maxLength = 200;
    input.required = true;
    input.setAttribute("aria-label", label);
    return input;
  }

  function buildEditingRow(rule) {
    const row = buildElement("tr");
    const nameInput = buildTextInput(rule.name, "Name");
    const queryInput = buildTextInput(rule.query, "Query");
    row.append(
      buildCell(nameInput),
      buildCell(queryInput),
      buildCell(rule.is_enabled ? "yes" : "no"),
      buildCell(describeBaseline(rule)),
      buildCell(
        buildButton("Save", () => saveRuleEdit(rule, nameInput.value.trim(), queryInput.value.trim())),
        buildButton("Cancel", () => stopEditingRule()),
      ),
    );
    return row;
  }

  function renderKeywords(rules) {
    keywordRowsElement.replaceChildren(
      ...rules.map((rule) => (rule.id === editingRuleId ? buildEditingRow(rule) : buildDisplayRow(rule))),
    );
  }

  function startEditingRule(ruleId) {
    editingRuleId = ruleId;
    renderKeywords(keywordRules);
  }

  function stopEditingRule() {
    editingRuleId = null;
    renderKeywords(keywordRules);
  }

  function collectRuleChanges(rule, name, query) {
    const changes = {};
    if (name !== rule.name) {
      changes.name = name;
    }
    if (query !== rule.query) {
      changes.query = query;
    }
    return changes;
  }

  function describeEditConsequence(changes) {
    if ("query" in changes) {
      return "The query changes, so this rule's baseline is re-seeded on the next cycle. " +
        "No alerts fire for listings that already match the new query. Save?";
    }
    return "Only the display name changes. The baseline is kept. Save?";
  }

  async function saveRuleEdit(rule, name, query) {
    const changes = collectRuleChanges(rule, name, query);
    if (Object.keys(changes).length === 0) {
      stopEditingRule();
      return;
    }
    if (!window.confirm(describeEditConsequence(changes))) {
      return;
    }
    await runAction(async () => {
      await requestJson("PATCH", "/api/keywords/" + rule.id, changes);
      editingRuleId = null;
      await refreshKeywords();
    }, "Rule saved");
  }

  async function resetRuleBaseline(rule) {
    const question = "Reset the baseline of \"" + rule.name + "\"? " +
      "It is re-seeded on the next cycle and sends no alerts for listings that already exist.";
    if (!window.confirm(question)) {
      return;
    }
    await runAction(async () => {
      await requestJson("POST", "/api/keywords/" + rule.id + "/reset-baseline");
      await refreshKeywords();
    }, "Baseline reset");
  }

  async function deleteRule(rule) {
    const question = "Delete \"" + rule.name + "\"? Its listing history and seen item IDs are kept.";
    if (!window.confirm(question)) {
      return;
    }
    await runAction(async () => {
      await requestJson("DELETE", "/api/keywords/" + rule.id);
      await refreshKeywords();
    }, "Rule deleted");
  }

  async function refreshKeywords() {
    keywordRules = await requestJson("GET", "/api/keywords");
    renderKeywords(keywordRules);
    updateEstimatedLatency();
  }

  async function createRule(event) {
    event.preventDefault();
    const formFields = keywordCreateForm.elements;
    await runAction(async () => {
      await requestJson("POST", "/api/keywords", {
        name: formFields.name.value.trim(),
        query: formFields.query.value.trim(),
        is_enabled: formFields.is_enabled.checked,
      });
      keywordCreateForm.reset();
      await refreshKeywords();
    }, "Rule added. Its baseline seeds on the next cycle.");
  }

  async function importKeywordRules(event) {
    event.preventDefault();
    await runAction(async () => {
      const result = await requestJson("POST", "/api/actions/import-yaml", {
        document_text: keywordImportForm.elements.document_text.value,
      });
      keywordImportForm.reset();
      await refreshKeywords();
      showMessage(
        "Imported " + result.imported_rule_count + " rules, skipped " + result.skipped_rule_count,
        false,
      );
    });
  }

  async function sendTestNotification() {
    await runAction(
      () => requestJson("POST", "/api/actions/test-notification"),
      "Test alert sent",
    );
  }

  function renderSettings(settings) {
    const formFields = settingsForm.elements;
    formFields.polling_gap_seconds.value = settings.polling_gap_seconds;
    formFields.is_item_detail_fetch_enabled.checked = settings.is_item_detail_fetch_enabled;
    formFields.max_images_per_alert.value = settings.max_images_per_alert;
    formFields.consecutive_failure_alert_threshold.value = settings.consecutive_failure_alert_threshold;
    formFields.system_alert_cooldown_seconds.value = settings.system_alert_cooldown_seconds;
    updateEstimatedLatency();
  }

  function readSettingsForm() {
    const formFields = settingsForm.elements;
    return {
      polling_gap_seconds: Number(formFields.polling_gap_seconds.value),
      is_item_detail_fetch_enabled: formFields.is_item_detail_fetch_enabled.checked,
      max_images_per_alert: Number(formFields.max_images_per_alert.value),
      consecutive_failure_alert_threshold: Number(formFields.consecutive_failure_alert_threshold.value),
      system_alert_cooldown_seconds: Number(formFields.system_alert_cooldown_seconds.value),
    };
  }

  function updateEstimatedLatency() {
    const pollingGapSeconds = Number(settingsForm.elements.polling_gap_seconds.value) || 0;
    const enabledRuleCount = countEnabledRules();
    estimatedLatencyElement.textContent =
      pollingGapSeconds * enabledRuleCount + " s (" + pollingGapSeconds + " s gap × " +
      enabledRuleCount + " enabled rules)";
  }

  async function refreshSettings() {
    renderSettings(await requestJson("GET", "/api/settings"));
  }

  async function saveSettings(event) {
    event.preventDefault();
    await runAction(async () => {
      renderSettings(await requestJson("PUT", "/api/settings", readSettingsForm()));
    }, "Settings saved");
  }

  function refreshAll() {
    return runAction(() => Promise.all([refreshKeywords(), refreshSettings()]));
  }

  keywordCreateForm.addEventListener("submit", createRule);
  keywordImportForm.addEventListener("submit", importKeywordRules);
  testNotificationButton.addEventListener("click", sendTestNotification);
  settingsForm.addEventListener("submit", saveSettings);
  settingsForm.elements.polling_gap_seconds.addEventListener("input", updateEstimatedLatency);

  refreshAll();
})();
