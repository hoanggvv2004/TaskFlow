(function () {
  const csrf = document.querySelector('meta[name="csrf-token"]')?.getAttribute("content");
  const ICONS = { success: "bi-check-circle-fill", error: "bi-x-circle-fill", info: "bi-info-circle-fill" };

  window.taskflow = {
    csrf,
    headers(extra) {
      return Object.assign({ "X-CSRFToken": csrf, "X-Requested-With": "XMLHttpRequest" }, extra || {});
    },
    toast(message, type) {
      const stack = document.getElementById("toastStack");
      if (!stack) return;
      const kind = type === "error" ? "error" : type === "info" ? "info" : "success";
      const el = document.createElement("div");
      el.className = "app-toast " + kind;
      el.innerHTML = `<i class="bi ${ICONS[kind]}"></i><span></span>`;
      el.querySelector("span").textContent = message;
      stack.appendChild(el);
      setTimeout(() => {
        el.classList.add("hide");
        setTimeout(() => el.remove(), 240);
      }, 2800);
    },
    async post(url, data, json) {
      const options = {
        method: "POST",
        headers: this.headers(json ? { "Content-Type": "application/json" } : {}),
        body: json ? JSON.stringify(data) : data,
      };
      const response = await fetch(url, options);
      const payload = await response.json().catch(() => ({ success: false, message: "Không thể xử lý phản hồi." }));
      if (!response.ok || payload.success === false) {
        throw new Error(payload.message || "Yêu cầu thất bại.");
      }
      return payload;
    },
    escape(str) {
      return String(str ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
    },
    badgeClass: {
      low: "badge-low", medium: "badge-medium", high: "badge-high", urgent: "badge-urgent",
      planning: "badge-muted", active: "badge-info", "on-hold": "badge-medium", completed: "badge-success", cancelled: "badge-danger",
      todo: "badge-muted", "in-progress": "badge-info", review: "badge-medium", blocked: "badge-danger",
    },
  };

  const quickProject = document.querySelector('#createTaskModal select[name="project_id"]');
  const quickType = document.getElementById("quickTaskType");
  const typeOptions = document.getElementById("quickTaskTypeOptions");
  if (quickProject && quickType && typeOptions) {
    const refreshTaskTypes = () => {
      quickType.length = 1;
      for (const option of typeOptions.content.querySelectorAll("option")) {
        if (option.dataset.project === quickProject.value) quickType.add(option.cloneNode(true));
      }
      quickType.disabled = quickType.length === 1;
    };
    quickProject.addEventListener("change", refreshTaskTypes);
    refreshTaskTypes();
  }

  /* ---------- Chart.js defaults ---------- */
  if (window.Chart) {
    Chart.defaults.font.family = 'Inter, system-ui, -apple-system, "Segoe UI", sans-serif';
    Chart.defaults.font.size = 12;
    Chart.defaults.color = "#6B7280";
    Chart.defaults.plugins.legend.labels.boxWidth = 10;
    Chart.defaults.plugins.legend.labels.boxHeight = 10;
    Chart.defaults.plugins.legend.labels.usePointStyle = true;
    Chart.defaults.plugins.legend.position = "bottom";
    Chart.defaults.plugins.tooltip.backgroundColor = "#111827";
    Chart.defaults.plugins.tooltip.padding = 10;
    Chart.defaults.plugins.tooltip.cornerRadius = 8;
    Chart.defaults.plugins.tooltip.displayColors = false;
    Chart.defaults.maintainAspectRatio = false;
    Chart.defaults.responsive = true;
    Chart.defaults.animation.duration = 600;
    Chart.defaults.animation.easing = "easeOutQuart";
    Chart.defaults.elements.bar.borderRadius = 6;
    Chart.defaults.elements.line.tension = 0.35;
    Chart.defaults.elements.point.radius = 3;
    Chart.defaults.elements.point.hoverRadius = 5;
    Chart.defaults.scale.grid.color = "rgba(107,114,128,.12)";
    Chart.defaults.scale.border = { display: false };
    window.taskflow.palette = ["#5B6CFF", "#10B981", "#F59E0B", "#EF4444", "#7C3AED", "#0EA5E9", "#9CA3AF"];
    window.taskflow.priorityColors = { low: "#34D399", medium: "#FBBF24", high: "#FB923C", urgent: "#F87171" };
    window.taskflow.statusColors = { todo: "#9CA3AF", "in-progress": "#5B6CFF", review: "#F59E0B", completed: "#10B981",
      paused: "#D97706", delayed: "#EF4444", rework: "#F97316", rejected: "#9F1239" };
    window.taskflow.labelFor = function (slug) {
      const map = {
        todo: "Mới", "in-progress": "Đang làm", review: "Chờ duyệt", completed: "Đã duyệt",
        paused: "Tạm hoãn", delayed: "Báo chậm", rework: "Cần làm lại", rejected: "Đã từ chối",
        low: "Low", medium: "Medium", high: "High", urgent: "Urgent",
      };
      return map[slug] || slug;
    };
  }

  /* ---------- Sidebar ---------- */
  const sidebar = document.getElementById("appSidebar");
  const toggle = document.getElementById("sidebarToggle");
  const overlay = document.getElementById("sidebarOverlay");
  const isMobile = () => window.innerWidth < 992;
  if (sidebar && toggle) {
    if (localStorage.getItem("tf-sidebar") === "1" && !isMobile()) sidebar.classList.add("collapsed");
    toggle.addEventListener("click", () => {
      if (isMobile()) {
        sidebar.classList.toggle("open");
        overlay?.classList.toggle("show", sidebar.classList.contains("open"));
      } else {
        sidebar.classList.toggle("collapsed");
        localStorage.setItem("tf-sidebar", sidebar.classList.contains("collapsed") ? "1" : "0");
        window.dispatchEvent(new Event("resize"));
      }
    });
    overlay?.addEventListener("click", () => {
      sidebar.classList.remove("open");
      overlay.classList.remove("show");
    });
  }

  /* ---------- Theme ---------- */
  const themeBtn = document.getElementById("themeToggle");
  const applyThemeIcon = () => {
    if (!themeBtn) return;
    const dark = document.documentElement.getAttribute("data-theme") === "dark";
    themeBtn.innerHTML = `<i class="bi ${dark ? "bi-sun" : "bi-moon"}"></i>`;
    themeBtn.title = dark ? "Light mode" : "Dark mode";
  };
  document.documentElement.setAttribute("data-theme", localStorage.getItem("tf-theme") || "light");
  applyThemeIcon();
  themeBtn?.addEventListener("click", () => {
    const next = document.documentElement.getAttribute("data-theme") === "dark" ? "light" : "dark";
    document.documentElement.setAttribute("data-theme", next);
    localStorage.setItem("tf-theme", next);
    applyThemeIcon();
  });

  /* ---------- Password toggle ---------- */
  document.querySelectorAll("[data-toggle-password]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const input = document.querySelector(btn.getAttribute("data-toggle-password"));
      if (!input) return;
      const show = input.type === "password";
      input.type = show ? "text" : "password";
      btn.innerHTML = `<i class="bi ${show ? "bi-eye-slash" : "bi-eye"}"></i>`;
    });
  });

  /* ---------- Page progress + button loading ---------- */
  const progress = document.getElementById("pageProgress");
  const startProgress = () => {
    if (!progress) return;
    progress.classList.add("active");
    progress.style.width = "70%";
  };
  window.addEventListener("beforeunload", startProgress);
  document.addEventListener("submit", (e) => {
    const form = e.target;
    if (form.hasAttribute("data-ajax") || form.id === "commentForm" || form.id === "checklistForm" || form.id === "attachmentForm") return;
    const btn = form.querySelector("button[type=submit], button:not([type])");
    if (btn && !btn.classList.contains("is-loading")) {
      btn.classList.add("is-loading");
      setTimeout(() => btn.classList.remove("is-loading"), 6000);
    }
  });

  /* ---------- Global search ---------- */
  const searchInput = document.getElementById("globalSearch");
  const searchBox = document.getElementById("searchResults");
  let searchTimer = null;
  const skeleton = `<div class="search-group">${'<div class="skeleton sk-line w-60"></div><div class="skeleton sk-line w-40"></div>'.repeat(2)}</div>`;
  if (searchInput && searchBox) {
    document.addEventListener("keydown", (e) => {
      if (e.key === "/" && !["INPUT", "TEXTAREA", "SELECT"].includes(document.activeElement?.tagName)) {
        e.preventDefault();
        searchInput.focus();
      }
      if (e.key === "Escape") searchBox.classList.remove("show");
    });
    searchInput.addEventListener("input", () => {
      clearTimeout(searchTimer);
      const q = searchInput.value.trim();
      if (q.length < 2) {
        searchBox.classList.remove("show");
        return;
      }
      searchBox.innerHTML = skeleton;
      searchBox.classList.add("show");
      searchTimer = setTimeout(async () => {
        try {
          const res = await fetch(`/search/api/search/?q=${encodeURIComponent(q)}`);
          const data = await res.json();
          const esc = window.taskflow.escape;
          const section = (title, icon, items) => {
            if (!items.length) return "";
            return `<div class="search-group"><h6>${title}</h6>${items
              .map(
                (i) =>
                  `<a class="search-item" href="${i.url}"><i class="bi ${icon}"></i><span>${esc(i.name)}</span>${
                    i.code ? `<span class="code ms-auto">${esc(i.code)}</span>` : i.email ? `<span class="code ms-auto">${esc(i.email)}</span>` : ""
                  }</a>`
              )
              .join("")}</div>`;
          };
          const html =
            section("Projects", "bi-folder2", data.projects) +
            section("Tasks", "bi-check2-square", data.tasks) +
            section("Members", "bi-person", data.members);
          searchBox.innerHTML = html || `<div class="search-empty"><i class="bi bi-search me-1"></i>Không có kết quả cho “${esc(q)}”</div>`;
        } catch (err) {
          searchBox.innerHTML = `<div class="search-empty">Không thể tìm kiếm lúc này.</div>`;
        }
      }, 220);
    });
    document.addEventListener("click", (e) => {
      if (!searchBox.contains(e.target) && e.target !== searchInput) searchBox.classList.remove("show");
    });
  }

  /* ---------- Notifications ---------- */
  const badge = document.getElementById("notifBadge");
  const setBadge = (n) => {
    if (!badge) return;
    badge.textContent = n > 99 ? "99+" : n;
    badge.classList.toggle("is-empty", !n);
  };
  if (badge) setBadge(parseInt(badge.textContent || "0", 10));

  document.querySelectorAll("[data-mark-read]").forEach((el) => {
    el.addEventListener("click", async (e) => {
      e.preventDefault();
      const id = el.getAttribute("data-mark-read");
      const url = el.getAttribute("data-url") || "#";
      try {
        const data = await window.taskflow.post(`/notifications/${id}/read/`, {});
        el.classList.remove("notif-unread");
        setBadge(data.unread ?? 0);
      } catch (err) {
        /* fall through to navigation */
      }
      if (url && url !== "#") window.location.href = url;
    });
  });

  document.querySelectorAll("#markAllRead, [data-mark-all-read]").forEach((btn) => {
    btn.addEventListener("click", async (e) => {
      e.preventDefault();
      e.stopPropagation();
      try {
        const data = await window.taskflow.post("/notifications/read-all/", {});
        window.taskflow.toast(data.message || "Đã đánh dấu tất cả là đã đọc.");
        document.querySelectorAll(".notif-unread").forEach((el) => el.classList.remove("notif-unread"));
        setBadge(0);
      } catch (err) {
        window.taskflow.toast(err.message, "error");
      }
    });
  });

  /* ---------- Confirm dialogs ---------- */
  document.querySelectorAll("[data-confirm]").forEach((el) => {
    el.addEventListener("click", (e) => {
      e.preventDefault();
      const form = el.closest("form");
      Swal.fire({
        title: el.getAttribute("data-confirm") || "Xác nhận thao tác?",
        text: el.getAttribute("data-confirm-text") || "Hãy kiểm tra kỹ trước khi tiếp tục.",
        icon: "warning",
        iconColor: "#F59E0B",
        showCancelButton: true,
        confirmButtonColor: "#5B6CFF",
        cancelButtonColor: "#E5E7EB",
        cancelButtonText: "Hủy",
        confirmButtonText: "Đồng ý",
        reverseButtons: true,
        customClass: { popup: "tf-swal", cancelButton: "text-dark" },
      }).then((result) => {
        if (result.isConfirmed) {
          if (form) form.submit();
          else if (el.href) window.location.href = el.href;
        }
      });
    });
  });

  /* ---------- Dropzone (file inputs) ---------- */
  document.querySelectorAll(".dropzone").forEach((zone) => {
    const input = zone.querySelector("input[type=file]");
    const label = zone.querySelector("[data-dz-label]");
    if (!input) return;
    const setLabel = () => {
      if (label && input.files.length) label.textContent = input.files[0].name;
    };
    zone.addEventListener("click", (e) => {
      if (e.target !== input) input.click();
    });
    ["dragenter", "dragover"].forEach((ev) => zone.addEventListener(ev, (e) => { e.preventDefault(); zone.classList.add("drag"); }));
    ["dragleave", "drop"].forEach((ev) => zone.addEventListener(ev, (e) => { e.preventDefault(); zone.classList.remove("drag"); }));
    zone.addEventListener("drop", (e) => {
      if (e.dataTransfer?.files?.length) {
        input.files = e.dataTransfer.files;
        setLabel();
      }
    });
    input.addEventListener("change", setLabel);
  });

  /* ---------- Animate progress bars ---------- */
  requestAnimationFrame(() => {
    document.querySelectorAll(".progress-thin > div[data-width]").forEach((bar) => {
      bar.style.width = bar.getAttribute("data-width") + "%";
    });
  });
})();
