// static/js/main.js
/**
 * Carrinho robusto:
 * - Salva no localStorage: id, nome, valor, quantidade
 * - Modal renderiza SEM depender de /api/produtos (isso elimina o "badge tem itens mas modal vazio")
 */

function _getCarrinho() {
  // COMENTÁRIO: sempre retorna array válido
  try {
    const raw = localStorage.getItem("carrinho");
    const data = raw ? JSON.parse(raw) : [];
    return Array.isArray(data) ? data : [];
  } catch (e) {
    console.error("Carrinho corrompido no localStorage, resetando.", e);
    localStorage.removeItem("carrinho");
    return [];
  }
}

function _setCarrinho(carrinho) {
  localStorage.setItem("carrinho", JSON.stringify(carrinho));
}

/**
 * Atualiza o badge com total de itens (somatório das quantidades)
 */
function atualizarIconeCarrinho() {
  const carrinho = _getCarrinho();
  const totalItens = carrinho.reduce((sum, item) => sum + Number(item.quantidade || 0), 0);

  const cartCount = document.getElementById("cartCount");
  if (cartCount) {
    cartCount.textContent = String(totalItens);
    if (totalItens > 0) cartCount.parentElement.classList.add("has-items");
    else cartCount.parentElement.classList.remove("has-items");
  }
}

/**
 * Adiciona produto ao carrinho.
 * Agora recebemos também nome e valor no clique (templates).
 *
 * @param {number} id
 * @param {string} nome
 * @param {number|string} valor
 */
function adicionarCarrinho(id, nome, valor) {
  // COMENTÁRIO: normaliza tipos para evitar mismatch
  id = Number(id);
  nome = String(nome || "").trim();

  // Valor pode vir como "12.34" (string do template) -> converte
  const valorNum = Number(valor);

  let carrinho = _getCarrinho();

  // Procura item já existente
  const existente = carrinho.find(i => Number(i.id) === id);

  if (existente) {
    existente.quantidade = Number(existente.quantidade || 0) + 1;

    // COMENTÁRIO: garante que nome/valor sempre fiquem atualizados
    if (nome) existente.nome = nome;
    if (!Number.isNaN(valorNum)) existente.valor = valorNum;
  } else {
    carrinho.push({
      id: id,
      nome: nome || `Produto #${id}`,
      valor: Number.isNaN(valorNum) ? 0 : valorNum,
      quantidade: 1
    });
  }

  _setCarrinho(carrinho);
  atualizarIconeCarrinho();
  mostrarNotificacao("Produto adicionado ao carrinho!");
}

/**
 * Remove 1 unidade do item, ou remove o item inteiro se chegar em 0
 */
function removerDoCarrinho(id) {
  id = Number(id);
  let carrinho = _getCarrinho();

  const idx = carrinho.findIndex(i => Number(i.id) === id);
  if (idx === -1) return;

  const q = Number(carrinho[idx].quantidade || 0);
  if (q > 1) carrinho[idx].quantidade = q - 1;
  else carrinho.splice(idx, 1);

  _setCarrinho(carrinho);
  atualizarIconeCarrinho();
  mostrarCarrinho(); // Atualiza modal
}

/**
 * Fecha modal
 */
function fecharCarrinho() {
  const modal = document.getElementById("carrinhoModal");
  if (modal) modal.style.display = "none";
}

/**
 * Abre modal e renderiza carrinho SEM depender de API.
 */
function mostrarCarrinho() {
  const carrinho = _getCarrinho();

  const carrinhoItensEl = document.getElementById("carrinhoItens");
  if (!carrinhoItensEl) {
    console.error("Elemento #carrinhoItens não encontrado no HTML.");
    alert("Erro ao abrir carrinho: estrutura do modal não encontrada.");
    return;
  }

  let total = 0;

  let html = `<h3 class="modal-title">Seu Carrinho</h3>`;

  if (carrinho.length === 0) {
    html += `<p class="empty-cart">Seu carrinho está vazio.</p>`;
    carrinhoItensEl.innerHTML = html;

    const modal = document.getElementById("carrinhoModal");
    if (modal) modal.style.display = "flex";
    return;
  }

  html += `<ul class="carrinho-lista">`;

  // COMENTÁRIO: renderiza sempre, porque agora temos nome/valor no localStorage
  const itensParaWhats = carrinho.map(item => {
    const nome = String(item.nome || `Produto #${item.id}`);
    const quantidade = Number(item.quantidade || 0);
    const valorUnit = Number(item.valor || 0);

    const subtotal = valorUnit * quantidade;
    total += subtotal;

    html += `
      <li class="carrinho-item">
        <span>${quantidade}x ${nome}</span>
        <span>R$ ${subtotal.toFixed(2)}</span>
        <button class="btn-remove" onclick="removerDoCarrinho(${Number(item.id)})">Remover</button>
      </li>
    `;

    return {
      nome: nome,
      quantidade: quantidade,
      valor_unitario: valorUnit
    };
  });

  html += `</ul>`;
  html += `<h4 class="carrinho-total">Total: R$ ${total.toFixed(2)}</h4>`;
  html += `<button class="btn-primary carrinho-btn" onclick='enviarWhatsApp(${JSON.stringify(itensParaWhats)})'>Entrar em Contato</button>`;

  carrinhoItensEl.innerHTML = html;

  const modal = document.getElementById("carrinhoModal");
  if (modal) modal.style.display = "flex";
}

/**
 * Envia itens para backend gerar o link do WhatsApp
 */
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

    // Abre WhatsApp
    window.open(data.url, "_blank");

    // Limpa carrinho após envio
    localStorage.removeItem("carrinho");
    atualizarIconeCarrinho();
    fecharCarrinho();
  } catch (error) {
    console.error("Erro:", error);
    alert("Erro de conexão. Verifique sua internet.");
  }
}

/**
 * Busca produtos na página
 */
function buscarProdutos() {
  const inputEl = document.getElementById("searchInput");
  const input = (inputEl ? inputEl.value : "").toLowerCase();
  const grid = document.getElementById("produtosGrid");
  if (!grid) return;

  const cards = grid.querySelectorAll(".card-produto");
  cards.forEach(card => {
    const title = card.querySelector(".card-title").textContent.toLowerCase();
    card.style.display = title.includes(input) ? "block" : "none";
  });
}

/**
 * Toast simples
 */
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

/**
 * Fecha modal ao clicar fora
 */
function fecharModalAoClicar(event) {
  const modal = document.getElementById("carrinhoModal");
  if (modal && event.target === modal) fecharCarrinho();
}

/**
 * Animações do toast
 */
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

/**
 * Inicializa
 */
window.addEventListener("load", () => {
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

/**
 * Sincroniza badge com outras abas
 */
setInterval(() => {
  atualizarIconeCarrinho();
}, 2000);

// ===== Mobile navigation =====
function toggleNavMenu() {
  const nav = document.getElementById("siteNav");
  if (!nav) return;
  nav.classList.toggle("open");
}

window.addEventListener("resize", () => {
  const nav = document.getElementById("siteNav");
  if (nav && window.innerWidth > 800) nav.classList.remove("open");
});
