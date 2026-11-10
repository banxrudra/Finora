/* Finora — UI interactions (no framework) */
(function () {
  "use strict";

  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => Array.from(r.querySelectorAll(s));
  const csrf = () => $('meta[name="csrf-token"]')?.content || "";

  const icons = () => window.lucide && window.lucide.createIcons();
  window.FinoraIcons = icons;

  /* ---------------------------------------------------------- theme */
  const root = document.documentElement;
  function applyTheme(pref) {
    const dark = pref === "dark" || (pref === "system" && matchMedia("(prefers-color-scheme: dark)").matches);
    root.dataset.theme = dark ? "dark" : "light";
    root.dataset.themePref = pref;
    try { localStorage.setItem("finora-theme", pref); } catch (e) { /* storage unavailable */ }
    document.dispatchEvent(new CustomEvent("themechange"));
    $$("[data-theme-icon]").forEach((el) => { el.hidden = el.dataset.themeIcon !== (dark ? "dark" : "light"); });
  }
  window.FinoraApplyTheme = applyTheme;

  matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => {
    if (root.dataset.themePref === "system") applyTheme("system");
  });

  $$("[data-theme-toggle]").forEach((btn) => btn.addEventListener("click", () => {
    const next = root.dataset.theme === "dark" ? "light" : "dark";
    applyTheme(next);
    fetch(btn.dataset.url, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-CSRFToken": csrf() },
      body: JSON.stringify({ theme: next }),
    }).catch(() => {});
  }));

  /* ---------------------------------------------------- mobile nav */
  $$("[data-nav-open]").forEach((b) => b.addEventListener("click", () => document.body.classList.add("nav-open")));
  $$("[data-nav-close]").forEach((b) => b.addEventListener("click", () => document.body.classList.remove("nav-open")));

  /* ------------------------------------------------------ dropdowns */
  function closeMenus(except) {
    $$("[data-dropdown]").forEach((d) => {
      if (d === except) return;
      const m = $("[data-menu]", d);
      const t = $("[data-dropdown-toggle]", d);
      if (m) m.hidden = true;
      if (t) t.setAttribute("aria-expanded", "false");
    });
  }
  $$("[data-dropdown]").forEach((d) => {
    const t = $("[data-dropdown-toggle]", d);
    const m = $("[data-menu]", d);
    t.addEventListener("click", (e) => {
      e.stopPropagation();
      const open = m.hidden;
      closeMenus(d);
      m.hidden = !open;
      t.setAttribute("aria-expanded", String(open));
    });
    m.addEventListener("click", (e) => e.stopPropagation());
  });
  document.addEventListener("click", () => closeMenus());
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") { closeMenus(); document.body.classList.remove("nav-open"); }
  });

  /* --------------------------------------------------------- toasts */
  const toastIcon = { success: "check", error: "x", info: "info" };
  function toast(msg, type = "info") {
    const box = $(".toasts");
    if (!box) return;
    const el = document.createElement("div");
    el.className = `toast toast-${type}`;
    el.setAttribute("role", type === "error" ? "alert" : "status");
    el.innerHTML = `<span class="toast-icon"><i data-lucide="${toastIcon[type] || "info"}"></i></span>
      <div class="toast-msg"></div>
      <button class="icon-btn icon-btn-sm" aria-label="Dismiss"><i data-lucide="x"></i></button>`;
    $(".toast-msg", el).textContent = msg;
    const close = () => { el.classList.add("is-leaving"); setTimeout(() => el.remove(), 200); };
    $("button", el).addEventListener("click", close);
    box.appendChild(el);
    icons();
    setTimeout(close, type === "error" ? 7000 : 4500);
  }
  window.FinoraToast = toast;
  $$("script[data-flash]").forEach((s) => {
    try { JSON.parse(s.textContent).forEach(([cat, msg]) => toast(msg, cat === "message" ? "info" : cat)); } catch (e) { /* ignore */ }
  });

  /* --------------------------------------------------------- modals */
  function openModal(id) {
    const d = document.getElementById(id);
    if (!d) return null;
    if (typeof d.showModal === "function") d.showModal(); else d.setAttribute("open", "");
    const first = $("[autofocus], input:not([type=hidden]):not([type=radio]), select, textarea", d);
    if (first) setTimeout(() => first.focus(), 30);
    return d;
  }
  $$("dialog.modal").forEach((d) => {
    d.addEventListener("click", (e) => { if (e.target === d) d.close(); }); // backdrop
    $$("[data-modal-close]", d).forEach((b) => b.addEventListener("click", () => d.close()));
  });

  // Fill a form from a JSON payload: { field: value }
  function fill(form, data) {
    Object.entries(data).forEach(([k, v]) => {
      const els = $$(`[name="${k}"]`, form);
      els.forEach((el) => {
        if (el.type === "radio" || el.type === "checkbox") el.checked = String(el.value) === String(v);
        else el.value = v == null ? "" : v;
      });
    });
  }

  document.addEventListener("click", (e) => {
    const btn = e.target.closest("[data-modal-open]");
    if (!btn) return;
    e.preventDefault();
    closeMenus();
    const id = btn.dataset.modalOpen;
    const d = document.getElementById(id);
    if (!d) return;
    const form = $("form", d);
    if (form) {
      form.reset();
      if (form.dataset.defaults) fill(form, JSON.parse(form.dataset.defaults));
      if (btn.dataset.payload) fill(form, JSON.parse(btn.dataset.payload));
      form.action = btn.dataset.action || form.dataset.createAction || form.action;
    }
    $$("[data-mode]", d).forEach((el) => { el.hidden = el.dataset.mode !== (btn.dataset.action ? "edit" : "create"); });
    if (btn.dataset.title) { const t = $("[data-modal-title]", d); if (t) t.textContent = btn.dataset.title; }
    d.dispatchEvent(new CustomEvent("modal:open", { detail: btn.dataset }));
    openModal(id);
  });

  // Confirm dialog (delete etc.)
  document.addEventListener("click", (e) => {
    const btn = e.target.closest("[data-confirm]");
    if (!btn) return;
    e.preventDefault();
    const d = document.getElementById("confirm-modal");
    $("[data-confirm-title]", d).textContent = btn.dataset.confirmTitle || "Are you sure?";
    $("[data-confirm-text]", d).textContent = btn.dataset.confirmText || "This action cannot be undone.";
    $("[data-confirm-btn]", d).textContent = btn.dataset.confirmLabel || "Delete";
    $("form", d).action = btn.dataset.confirm;
    openModal("confirm-modal");
  });

  /* ------------------------------------------- transaction form logic */
  function syncCategories(form) {
    const kind = $('input[name="kind"]:checked', form)?.value || "expense";
    const sel = $('select[name="category_id"]', form);
    if (!sel) return;
    $$("optgroup", sel).forEach((g) => {
      const match = g.dataset.kind === kind;
      g.hidden = !match;
      g.disabled = !match;
    });
    const opt = sel.selectedOptions[0];
    if (opt && opt.parentElement.tagName === "OPTGROUP" && opt.parentElement.dataset.kind !== kind) sel.value = "";
  }
  $$("form[data-tx-form]").forEach((form) => {
    $$('input[name="kind"]', form).forEach((r) => r.addEventListener("change", () => syncCategories(form)));
    form.closest("dialog")?.addEventListener("modal:open", () => syncCategories(form));
    syncCategories(form);
  });

  /* ----------------------------------------------- category preview */
  $$("form[data-cat-form]").forEach((form) => {
    const prev = $("[data-cat-preview]", form);
    const update = () => {
      const icon = $('input[name="icon"]:checked', form)?.value || "tag";
      const color = $('input[name="color"]:checked', form)?.value || "#64748b";
      const name = $('input[name="name"]', form).value || "New category";
      prev.style.setProperty("--c", color);
      prev.querySelector(".cat-icon").innerHTML = `<i data-lucide="${icon}"></i>`;
      prev.querySelector(".cat-icon").style.setProperty("--c", color);
      prev.querySelector("[data-preview-name]").textContent = name;
      icons();
    };
    form.addEventListener("input", update);
    form.addEventListener("change", update);
    form.closest("dialog")?.addEventListener("modal:open", () => setTimeout(update));
  });

  /* ------------------------------------------------- misc behaviours */
  $$("[data-autosubmit]").forEach((el) => el.addEventListener("change", () => el.form.requestSubmit()));
  $$("[data-toggle]").forEach((b) => b.addEventListener("click", () => {
    const t = document.getElementById(b.dataset.toggle);
    t.hidden = !t.hidden;
    b.setAttribute("aria-expanded", String(!t.hidden));
  }));
  $$("[data-print]").forEach((b) => b.addEventListener("click", () => window.print()));

  // Debounced search submit
  $$("[data-search]").forEach((input) => {
    let t;
    input.addEventListener("input", () => {
      clearTimeout(t);
      t = setTimeout(() => input.form.requestSubmit(), 450);
    });
  });

  // Prevent double submit
  document.addEventListener("submit", (e) => {
    const b = e.target.querySelector('button[type="submit"]:not([data-allow-multi])');
    if (b) setTimeout(() => { b.disabled = true; }, 0);
  });

  window.addEventListener("pageshow", () => {
    $$('button[type="submit"]:disabled').forEach((b) => { b.disabled = false; });
  });

  icons();
})();
