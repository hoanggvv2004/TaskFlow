(function () {
  const root = document.getElementById("taskDetail");
  if (!root) return;
  const taskId = root.getAttribute("data-task-id");
  const esc = window.taskflow.escape;

  /* ---------- Comments ---------- */
  const commentForm = document.getElementById("commentForm");
  const commentList = document.getElementById("commentList");
  const commentCount = document.getElementById("commentCount");
  const bumpCount = (el, delta) => {
    if (!el) return;
    el.textContent = Math.max(0, parseInt(el.textContent || "0", 10) + delta);
  };

  const bindCommentActions = (scope) => {
    scope.querySelectorAll("[data-edit-comment]").forEach((btn) => {
      btn.onclick = async () => {
        const id = btn.getAttribute("data-edit-comment");
        const body = document.getElementById(`comment-body-${id}`);
        const { value } = await Swal.fire({
          title: "Sửa bình luận",
          input: "textarea",
          inputValue: body?.textContent || "",
          showCancelButton: true,
          confirmButtonText: "Lưu",
          cancelButtonText: "Hủy",
          confirmButtonColor: "#5B6CFF",
          reverseButtons: true,
        });
        if (!value || !value.trim()) return;
        const form = new FormData();
        form.append("content", value.trim());
        try {
          const data = await window.taskflow.post(`/tasks/comments/${id}/edit/`, form);
          if (body) body.textContent = data.content;
          window.taskflow.toast(data.message);
        } catch (err) {
          window.taskflow.toast(err.message, "error");
        }
      };
    });
    scope.querySelectorAll("[data-delete-comment]").forEach((btn) => {
      btn.onclick = async () => {
        const id = btn.getAttribute("data-delete-comment");
        const result = await Swal.fire({
          title: "Xóa bình luận?",
          icon: "warning",
          iconColor: "#F59E0B",
          showCancelButton: true,
          confirmButtonText: "Xóa",
          cancelButtonText: "Hủy",
          confirmButtonColor: "#EF4444",
          reverseButtons: true,
        });
        if (!result.isConfirmed) return;
        try {
          await window.taskflow.post(`/tasks/comments/${id}/delete/`, new FormData());
          const el = document.getElementById(`comment-${id}`);
          if (el) {
            el.style.transition = "opacity .2s, transform .2s";
            el.style.opacity = "0";
            el.style.transform = "translateX(8px)";
            setTimeout(() => el.remove(), 200);
          }
          bumpCount(commentCount, -1);
          window.taskflow.toast("Đã xóa bình luận.");
        } catch (err) {
          window.taskflow.toast(err.message, "error");
        }
      };
    });
  };
  bindCommentActions(document);

  if (commentForm) {
    commentForm.addEventListener("submit", async (e) => {
      e.preventDefault();
      const btn = commentForm.querySelector("button[type=submit]");
      const textarea = commentForm.querySelector("textarea");
      if (!textarea.value.trim()) {
        textarea.focus();
        return;
      }
      btn.classList.add("is-loading");
      try {
        const data = await window.taskflow.post(`/tasks/${taskId}/comments/`, new FormData(commentForm));
        const c = data.comment;
        const avatar = c.avatar
          ? `<img class="avatar" src="${c.avatar}" width="36" height="36" alt="">`
          : `<span class="avatar-fallback" style="width:36px;height:36px">${esc(c.initials)}</span>`;
        const item = document.createElement("div");
        item.className = "comment";
        item.id = `comment-${c.id}`;
        item.innerHTML = `${avatar}
          <div class="body">
            <div class="head"><strong>${esc(c.author)}</strong><time>${esc(c.created_at)}</time></div>
            <p class="content" id="comment-body-${c.id}">${esc(c.content)}</p>
            <div class="actions">
              <button type="button" data-edit-comment="${c.id}"><i class="bi bi-pencil"></i> Sửa</button>
              <button type="button" class="danger" data-delete-comment="${c.id}"><i class="bi bi-trash"></i> Xóa</button>
            </div>
          </div>`;
        const empty = commentList.querySelector(".empty-inline");
        if (empty) empty.remove();
        commentList.appendChild(item);
        bindCommentActions(item);
        bumpCount(commentCount, 1);
        commentForm.reset();
        window.taskflow.toast(data.message);
      } catch (err) {
        window.taskflow.toast(err.message, "error");
      } finally {
        btn.classList.remove("is-loading");
      }
    });
  }

  /* ---------- Checklist ---------- */
  const checklist = document.getElementById("checklist");
  const checkForm = document.getElementById("checklistForm");
  const checkSummary = document.getElementById("checkSummary");
  const checkBar = document.getElementById("checkBar");

  const refreshChecklistSummary = () => {
    if (!checklist) return;
    const boxes = checklist.querySelectorAll("input[type=checkbox]");
    const done = [...boxes].filter((b) => b.checked).length;
    if (checkSummary) checkSummary.textContent = `${done}/${boxes.length} hoàn thành`;
    if (checkBar) checkBar.style.width = (boxes.length ? Math.round((done / boxes.length) * 100) : 0) + "%";
  };

  checklist?.addEventListener("change", async (event) => {
    const box = event.target.closest("[data-toggle-check]");
    if (!box) return;
    const button = box.closest(".check-row").querySelector("[data-delete-check]");
    box.disabled = true;
    if (button) button.disabled = true;
    try {
      const data = await window.taskflow.post(`/tasks/checklist/${box.dataset.toggleCheck}/toggle/`, new FormData());
      box.checked = data.is_completed;
      refreshChecklistSummary();
    } catch (err) {
      box.checked = !box.checked;
      window.taskflow.toast(err.message, "error");
    } finally {
      box.disabled = false;
      if (button) button.disabled = false;
    }
  });

  checklist?.addEventListener("click", async (event) => {
    const button = event.target.closest("[data-delete-check]");
    if (!button || button.disabled) return;
    const row = button.closest(".check-row");
    const box = row.querySelector("[data-toggle-check]");
    button.disabled = true;
    box.disabled = true;
    try {
      const confirmed = window.Swal ? (await window.Swal.fire({
        title: "Xóa hạng mục checklist?",
        icon: "warning",
        showCancelButton: true,
        confirmButtonText: "Xóa",
        cancelButtonText: "Hủy",
        confirmButtonColor: "#EF4444",
        reverseButtons: true,
      })).isConfirmed : window.confirm("Xóa hạng mục checklist này?");
      if (!confirmed) return;
      const data = await window.taskflow.post(button.dataset.deleteCheck, new FormData());
      const adjacent = row.nextElementSibling || row.previousElementSibling;
      row.remove();
      refreshChecklistSummary();
      (adjacent?.querySelector("[data-delete-check]") || checkForm?.querySelector("[name=title]"))?.focus();
      window.taskflow.toast(data.message);
    } catch (err) {
      window.taskflow.toast(err.message, "error");
    } finally {
      box.disabled = false;
      button.disabled = false;
    }
  });
  refreshChecklistSummary();

  if (checkForm) {
    checkForm.addEventListener("submit", async (e) => {
      e.preventDefault();
      const input = checkForm.querySelector("input[name=title]");
      if (!input.value.trim()) return input.focus();
      try {
        const data = await window.taskflow.post(`/tasks/${taskId}/checklist/`, new FormData(checkForm));
        checklist.insertAdjacentHTML("beforeend", data.html);
        checkForm.reset();
        refreshChecklistSummary();
      } catch (err) {
        window.taskflow.toast(err.message, "error");
      }
    });
  }

  /* ---------- Attachments ---------- */
  const uploadForm = document.getElementById("attachmentForm");
  const attachList = document.getElementById("attachmentList");
  const attachCount = document.getElementById("attachCount");
  if (uploadForm) {
    uploadForm.addEventListener("submit", async (e) => {
      e.preventDefault();
      const input = uploadForm.querySelector("input[type=file]");
      if (!input.files.length) {
        window.taskflow.toast("Hãy chọn tệp trước khi tải lên.", "info");
        return;
      }
      const btn = uploadForm.querySelector("button[type=submit]");
      btn.classList.add("is-loading");
      try {
        const data = await window.taskflow.post(`/tasks/${taskId}/attachments/`, new FormData(uploadForm));
        const name = data.document.name;
        const ext = (name.split(".").pop() || "").toLowerCase();
        const li = document.createElement("div");
        li.className = "attach-item";
        li.style.animation = "fadeUp .25s ease";
        li.innerHTML = `<div class="file-icon file-${esc(ext)} file-default">${esc(ext.slice(0, 4))}</div>
          <div class="flex-grow-1 min-w-0"><span class="name">${esc(name)}</span><span class="meta">Vừa tải lên</span></div>
          <a class="btn btn-light btn-sm" href="${data.document.url}" target="_blank"><i class="bi bi-download"></i></a>`;
        const empty = attachList.querySelector(".empty-inline");
        if (empty) empty.remove();
        attachList.appendChild(li);
        bumpCount(attachCount, 1);
        uploadForm.reset();
        const label = uploadForm.querySelector("[data-dz-label]");
        if (label) label.textContent = "Kéo thả hoặc bấm để chọn tệp";
        window.taskflow.toast(data.message);
      } catch (err) {
        window.taskflow.toast(err.message, "error");
      } finally {
        btn.classList.remove("is-loading");
      }
    });
  }

  /* ---------- Status ---------- */
  const statusForm = document.getElementById("statusForm");
  if (statusForm) {
    statusForm.addEventListener("submit", async (event) => {
      event.preventDefault();
      const submit = statusForm.querySelector("button[type=submit]");
      submit.disabled = true;
      try {
        await window.taskflow.post(statusForm.action, Object.fromEntries(new FormData(statusForm)), true);
        window.location.reload();
      } catch (err) {
        window.taskflow.toast(err.message, "error");
        submit.disabled = false;
      }
    });
  }
})();
