// static/js/main.js
function _getCarrinho() {
  try {
    const raw = localStorage.getItem("carrinho");
    const data = raw ? JSON.parse(raw) : [];
    return Array.isArray(data) ? data : [];
  } catch (e) {
    localStorage.removeItem("carrinho");
    return [];
  }
}

function _setCarrinho(carrinho) {
  localStorage.setItem("carrinho", JSON.stringify(carrinho));
}

function atualizarIconeCarrinho() {
  const cartCount = document.getElementById("cartCount");
  if (!cartCount) return;

  const carrinho = _getCarrinho();
  const totalItens = carrinho.reduce((sum, item) => sum + Number(item.quantidade || 0), 0);
  cartCount.textContent = String(totalItens);

  if (!cartCount.parentElement) return;
  if (totalItens > 0) cartCount.parentElement.classList.add("has-items");
  else cartCount.parentElement.classList.remove("has-items");
}

function adicionarCarrinho(id, nome, valor) {
  void id;
  void nome;
  void valor;
  mostrarNotificacao("Consulte os produtos e fale com a equipe no WhatsApp.");
}

function removerDoCarrinho(id) {
  void id;
}

function fecharCarrinho() {
  const modal = document.getElementById("carrinhoModal");
  if (modal) modal.style.display = "none";
}

function mostrarCarrinho() {
  const carrinhoItensEl = document.getElementById("carrinhoItens");
  const modal = document.getElementById("carrinhoModal");
  if (!carrinhoItensEl || !modal) return;

  carrinhoItensEl.innerHTML = `
    <h3 class="modal-title">Atendimento comercial</h3>
    <p class="empty-cart">Consulte os produtos ou fale com a equipe pelo WhatsApp.</p>
  `;
  modal.style.display = "flex";
}

async function enviarWhatsApp(itens) {
  try {
    const res = await fetch("/api/whatsapp", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(itens)
    });

    if (!res.ok) {
      alert("Erro ao gerar link. Tente novamente.");
      return;
    }

    const data = await res.json();
    window.open(data.url, "_blank");
    localStorage.removeItem("carrinho");
    atualizarIconeCarrinho();
    fecharCarrinho();
  } catch (error) {
    console.error("Erro:", error);
    alert("Erro de conexao. Verifique sua internet.");
  }
}

function buscarProdutos() {
  const inputEl = document.getElementById("searchInput");
  const input = (inputEl ? inputEl.value : "").toLowerCase();
  const grid = document.getElementById("produtosGrid");
  if (!grid) return;

  const cards = grid.querySelectorAll(".card-produto");
  cards.forEach(card => {
    const titleEl = card.querySelector(".card-title");
    const title = titleEl ? titleEl.textContent.toLowerCase() : "";
    card.style.display = title.includes(input) ? "block" : "none";
  });

  const grupos = grid.querySelectorAll(".products-category-block");
  grupos.forEach(grupo => {
    const cardsDoGrupo = grupo.querySelectorAll(".card-produto");
    const temVisivel = Array.from(cardsDoGrupo).some(card => card.style.display !== "none");
    grupo.style.display = temVisivel ? "grid" : "none";
  });
}

function mostrarNotificacao(mensagem) {
  const notificacao = document.createElement("div");
  notificacao.className = "notificacao";
  notificacao.textContent = mensagem;
  document.body.appendChild(notificacao);

  setTimeout(() => {
    notificacao.style.animation = "slideOut 0.3s ease";
    setTimeout(() => notificacao.remove(), 300);
  }, 3000);
}

function fecharModalAoClicar(event) {
  const modal = document.getElementById("carrinhoModal");
  if (modal && event.target === modal) fecharCarrinho();
}

function adicionarAnimacoes() {
  const style = document.createElement("style");
  style.textContent = `
    @keyframes slideIn {
      from { transform: translateX(400px); opacity: 0; }
      to { transform: translateX(0); opacity: 1; }
    }
    @keyframes slideOut {
      from { transform: translateX(0); opacity: 1; }
      to { transform: translateX(400px); opacity: 0; }
    }
    .notificacao {
      position: fixed;
      bottom: 20px;
      right: 20px;
      background: var(--laranja);
      color: var(--branco);
      padding: var(--spacing-md);
      border-radius: 8px;
      box-shadow: var(--shadow-md);
      animation: slideIn 0.3s ease;
      z-index: 1001;
    }
  `;
  document.head.appendChild(style);
}

window.addEventListener("load", () => {
  if (localStorage.getItem("carrinho")) {
    localStorage.removeItem("carrinho");
  }

  atualizarIconeCarrinho();
  adicionarAnimacoes();

  const modal = document.getElementById("carrinhoModal");
  if (modal) modal.addEventListener("click", fecharModalAoClicar);

  const searchInput = document.getElementById("searchInput");
  if (searchInput) {
    searchInput.addEventListener("keypress", (e) => {
      if (e.key === "Enter") buscarProdutos();
    });
  }
});

function toggleNavMenu() {
  const nav = document.getElementById("siteNav");
  if (!nav) return;
  nav.classList.toggle("open");
}

window.addEventListener("resize", () => {
  const nav = document.getElementById("siteNav");
  if (nav && window.innerWidth > 1020) nav.classList.remove("open");
});
