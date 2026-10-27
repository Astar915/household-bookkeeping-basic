"use strict";

// Run before stylesheets: avoid a light flash when opening a dark installed PWA.
// The preference belongs to this device; never replace another device's choice
// during ledger sync, account changes, or a cloud restore.
(() => {
  const key = "household-appearance";
  const valid = value => ["system", "light", "dark"].includes(value);
  const system = window.matchMedia("(prefers-color-scheme: dark)");
  let mode = "system";
  try {
    const stored = localStorage.getItem(key);
    if (valid(stored)) mode = stored;
  } catch { /* Private browsing/storage restrictions still allow system mode. */ }
  function apply() {
    const resolved = mode === "system" ? (system.matches ? "dark" : "light") : mode;
    document.documentElement.dataset.theme = resolved;
    document.documentElement.dataset.appearance = mode;
    const updateChrome = () => {
      document.querySelectorAll('meta[name="theme-color"]').forEach(meta => {
        meta.removeAttribute("media");
        meta.content = resolved === "dark" ? "#11131b" : "#f5f6fa";
      });
    };
    updateChrome();
    window.dispatchEvent(new CustomEvent("appearancechange", {detail: {mode, resolved}}));
  }
  window.HouseholdAppearance = {
    get mode() { return mode; },
    save(value) {
      if (!valid(value)) throw new Error("Invalid appearance mode");
      // A failed save must leave both the existing preference and display intact.
      localStorage.setItem(key, value);
      mode = value;
      apply();
    },
  };
  if (system.addEventListener) system.addEventListener("change", () => { if (mode === "system") apply(); });
  else system.addListener(() => { if (mode === "system") apply(); });
  window.addEventListener("storage", event => {
    if (event.key === key || event.key === null) { mode = valid(event.newValue) ? event.newValue : "system"; apply(); }
  });
  document.addEventListener("DOMContentLoaded", () => {
    const launch = document.getElementById("appearanceButton");
    if (!launch) return;
    launch.onclick = () => {
      const lang = document.documentElement.lang;
      const text = (zh, ja, en) => lang.startsWith("ja") ? ja : lang.startsWith("en") ? en : zh;
      const dialog = document.createElement("dialog");
      dialog.className = "appearance-dialog";
      const form = document.createElement("form");
      const title = document.createElement("h2");
      title.textContent = text("外观", "外観", "Appearance");
      const label = document.createElement("label");
      label.className = "field";
      label.textContent = text("明暗模式", "表示モード", "Color mode");
      const select = document.createElement("select");
      for (const [value, caption] of [["system", text("跟随系统", "システム設定に従う", "Follow system")],
        ["light", text("浅色模式", "ライトモード", "Light mode")],
        ["dark", text("深色模式", "ダークモード", "Dark mode")]]) {
        const option = document.createElement("option");
        option.value = value; option.textContent = caption; select.append(option);
      }
      select.value = mode;
      label.append(select);
      const note = document.createElement("p");
      note.className = "fineprint";
      note.textContent = text("只影响当前设备。跟随系统会自动切换，点击应用或确认后保存。",
        "この端末のみに適用。「適用」または「確定」で保存します。",
        "Applies to this device. Follow system changes automatically. Apply or Done saves your choice.");
      const status = document.createElement("p");
      status.className = "fineprint"; status.setAttribute("role", "status");
      const row = document.createElement("div"); row.className = "button-row";
      function button(caption, primary, action) {
        const control = document.createElement("button"); control.type = "button";
        control.className = "button " + (primary ? "primary" : "secondary");
        control.textContent = caption; control.onclick = action; row.append(control);
      }
      const save = close => {
        try {
          window.HouseholdAppearance.save(select.value);
          if (close) dialog.close();
          else status.textContent = text("外观已应用", "外観を適用しました", "Appearance applied");
        } catch {
          status.textContent = text("无法保存外观，请检查浏览器的本机存储权限。",
            "外観を保存できません。ブラウザーのストレージ設定を確認してください。",
            "Could not save appearance. Check browser storage permissions.");
        }
      };
      button(text("取消", "キャンセル", "Cancel"), false, () => dialog.close());
      button(text("应用", "適用", "Apply"), false, () => save(false));
      button(text("确认", "確定", "Done"), true, () => save(true));
      form.onsubmit = event => { event.preventDefault(); save(true); };
      form.append(title, label, note, status, row); dialog.append(form);
      dialog.setAttribute("aria-label", title.textContent);
      dialog.addEventListener("close", () => dialog.remove(), {once: true});
      document.body.append(dialog); dialog.showModal();
    };
  });
  apply();
})();
