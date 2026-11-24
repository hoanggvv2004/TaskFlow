const addTransition = document.getElementById("addTransition");
const transitionTemplate = document.getElementById("transitionTemplate");
const transitionRows = document.getElementById("transitionRows");
const totalTransitions = document.getElementById("id_form-TOTAL_FORMS");

addTransition.addEventListener("click", () => {
  const index = Number(totalTransitions.value);
  transitionRows.insertAdjacentHTML("beforeend", transitionTemplate.innerHTML.replaceAll("__prefix__", index));
  totalTransitions.value = index + 1;
  transitionRows.lastElementChild.querySelector("select").focus();
});
