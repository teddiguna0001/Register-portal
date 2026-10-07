// Mobile hamburger menu
const burger = document.getElementById("burger"), menu = document.getElementById("menu");
burger.addEventListener("click", () => {
  const open = menu.classList.toggle("open");
  burger.setAttribute("aria-expanded", open);
});
menu.addEventListener("click", e => { if (e.target.closest("a")) menu.classList.remove("open"); });
