document.addEventListener("DOMContentLoaded", () => {
    const fotoItems = document.querySelectorAll(".foto-item img");

    // Создаём модальное окно
    const modal = document.createElement("div");
    modal.classList.add("modal");
    modal.innerHTML = `
        <span class="close-btn">&times;</span>
        <img src="" alt="Full Image">
    `;
    document.body.appendChild(modal);

    const modalImg = modal.querySelector("img");
    const closeBtn = modal.querySelector(".close-btn");

    // Открытие по клику на картинку
    fotoItems.forEach(img => {
        img.addEventListener("click", () => {
            modalImg.src = img.src;
            modal.classList.add("active");
        });
    });

    // Закрытие
    closeBtn.addEventListener("click", () => {
        modal.classList.remove("active");
    });

    modal.addEventListener("click", (e) => {
        if (e.target === modal) modal.classList.remove("active");
    });
});











