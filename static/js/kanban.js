(function () {
  const board = document.getElementById("kanbanBoard");
  if (!board || typeof Sortable === "undefined") return;

  const updateCounts = () => {
    board.querySelectorAll(".kanban-col").forEach((col) => {
      const count = col.querySelector("[data-col-count]");
      if (count) count.textContent = col.querySelectorAll(".task-card").length;
    });
  };

  board.querySelectorAll("[data-status-list]").forEach((list) => {
    new Sortable(list, {
      group: "tasks",
      animation: 180,
      easing: "cubic-bezier(0.2, 0.8, 0.2, 1)",
      ghostClass: "sortable-ghost",
      chosenClass: "sortable-chosen",
      dragClass: "sortable-drag",
      filter: '.is-saving, [data-allowed-status=""]',
      preventOnFilter: false,
      onMove: (evt) => {
        board.querySelectorAll(".kanban-list").forEach((l) => l.classList.remove("drag-over"));
        const targets = evt.dragged.dataset.allowedStatus.split(",");
        if (evt.to !== evt.from && !targets.includes(evt.to.dataset.statusList)) return false;
        evt.to.classList.add("drag-over");
      },
      onEnd: async (evt) => {
        board.querySelectorAll(".kanban-list").forEach((l) => l.classList.remove("drag-over"));
        const card = evt.item;
        const from = evt.from;
        if (evt.to === from && evt.oldIndex === evt.newIndex) return;
        if (evt.to === from) return;
        const taskId = card.getAttribute("data-task-id");
        const statusId = evt.to.getAttribute("data-status-list");
        card.classList.add("is-saving");
        try {
          const data = await window.taskflow.post(`/tasks/${taskId}/status/`, {
            status_id: statusId,
            source_id: from.dataset.statusList,
          }, true);
          card.dataset.allowedStatus = data.targets.join(",");
          window.taskflow.toast(data.message);
          updateCounts();
        } catch (err) {
          from.insertBefore(card, from.children[evt.oldIndex] || null);
          updateCounts();
          window.taskflow.toast(err.message || "Không thể cập nhật nhiệm vụ.", "error");
        } finally {
          card.classList.remove("is-saving");
        }
      },
    });
  });
})();
