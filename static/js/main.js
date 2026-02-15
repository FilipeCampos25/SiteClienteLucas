// static/js/main.js
/**
 * ============================================
 * CANTONEIRA FÁCIL - SCRIPT PRINCIPAL
 * Gerenciamento de carrinho, produtos e interações
 * ============================================
 */

/* ===== VARIÁVEIS GLOBAIS ===== */
let todosProdutos = [];

/**
 * Carrega todos os produtos da API uma única vez
 * Utiliza cache simples para melhor performance
 */
async function carregarProdutos() {
  // Se já foram carregados, não carrega novamente
  if (todosProdutos.length > 0) return;

  try {
    const res = await fetch('/api/produtos');

    if (res.ok) {
      todosProdutos = await res.json();
      window.todosProdutos = todosProdutos;
    } else {
      console.error("Erro carregando produtos:", res.status);
      alert("Falha ao carregar produtos. Tente recarregar a página.");
    }
  } catch (error) {
    console.error("Erro na requisição:", error);
    alert("Erro ao conectar com o servidor. Verifique sua conexão.");
  }
}

/**
 * Atualiza o ícone do carrinho com a quantidade de itens
 * Mostra/esconde o badge de contagem
 */
function atualizarIconeCarrinho() {
  const carrinho = JSON.parse(localStorage.getItem('carrinho') || '[]');

  // COMENTÁRIO: garante soma numérica mesmo se "quantidade" vier como string/undefined
  const totalItens = carrinho.reduce((sum, item) => sum + Number(item.quantidade || 0), 0);

  const cartCount = document.getElementById('cartCount');
  if (cartCount) {
    cartCount.textContent = totalItens;

    // Mostra/esconde o badge de contagem
    if (totalItens > 0) {
      cartCount.parentElement.classList.add('has-items');
    } else {
      cartCount.parentElement.classList.remove('has-items');
    }
  }
}

/**
 * Adiciona um produto ao carrinho (localStorage)
 * Se o produto já existe, incrementa a quantidade
 *
 * @param {number} id - ID do produto
 */
function adicionarCarrinho(id) {
  // COMENTÁRIO: garante ID numérico (no HTML pode vir como string)
  id = Number(id);

  let carrinho = JSON.parse(localStorage.getItem('carrinho') || '[]');

  // COMENTÁRIO: Number(i.id) mantém compatibilidade com carrinhos antigos salvos como string
  const existente = carrinho.find(i => Number(i.id) === id);

  if (existente) {
    existente.quantidade++;
  } else {
    carrinho.push({ id: id, quantidade: 1 }); // armazena id como número
  }

  localStorage.setItem('carrinho', JSON.stringify(carrinho));

  // Atualiza ícone
  atualizarIconeCarrinho();

  // Mostra notificação
  mostrarNotificacao('Produto adicionado ao carrinho!');
}

/**
 * Remove um item do carrinho ou decrementa quantidade
 *
 * @param {number} id - ID do produto
 */
function removerDoCarrinho(id) {
  // COMENTÁRIO: garante ID numérico (evita mismatch na busca/remocao)
  id = Number(id);

  let carrinho = JSON.parse(localStorage.getItem('carrinho') || '[]');

  // COMENTÁRIO: Number(i.id) para compatibilidade com carrinhos antigos salvos como string
  const index = carrinho.findIndex(i => Number(i.id) === id);

  if (index !== -1) {
    if (carrinho[index].quantidade > 1) {
      carrinho[index].quantidade--;
    } else {
      carrinho.splice(index, 1);
    }

    localStorage.setItem('carrinho', JSON.stringify(carrinho));
    atualizarIconeCarrinho();
    mostrarCarrinho(); // Atualiza o modal
  }
}

/**
 * Fecha o modal do carrinho
 */
function fecharCarrinho() {
  const modal = document.getElementById('carrinhoModal');
  if (modal) {
    modal.style.display = 'none';
  }
}

/**
 * Mostra o modal do carrinho com itens
 */
async function mostrarCarrinho() {
  await carregarProdutos(); // Garante que produtos estejam carregados

  let carrinho = JSON.parse(localStorage.getItem('carrinho') || '[]');

  // ==========================================================
  // FIX IMPORTANTE:
  // - Seu base.html tem <div id="carrinhoItens"></div>
  // - NÃO devemos sobrescrever ".modal-content", senão
  //   apagamos a estrutura original do modal e pode parecer vazio.
  // ==========================================================
  const carrinhoItensEl = document.getElementById('carrinhoItens');
  if (!carrinhoItensEl) {
    console.error("Elemento #carrinhoItens não encontrado no HTML.");
    alert("Erro ao abrir carrinho: estrutura do modal não encontrada.");
    return;
  }

  let html = '<h3 class="modal-title">Seu Carrinho</h3><ul class="carrinho-lista">';
  let total = 0;
  const itensParaWhats = [];

  // COMENTÁRIO: flag para detectar quando o carrinho tem itens,
  // mas não conseguimos mapear os produtos (ex: falha ao carregar /api/produtos)
  let encontrouAlgumProduto = false;

  carrinho.forEach(item => {
    // COMENTÁRIO: item.id pode estar como string no localStorage; converte para número
    const itemId = Number(item.id);

    // COMENTÁRIO: p.id vem como número do backend; agora a comparação fecha
    const prod = todosProdutos.find(p => p.id === itemId);

    if (prod) {
      encontrouAlgumProduto = true;

      const subtotal = Number(prod.valor) * Number(item.quantidade || 0);
      total += subtotal;

      html += `
        <li class="carrinho-item">
          <span>${Number(item.quantidade || 0)}x ${prod.nome}</span>
          <span>R$ ${subtotal.toFixed(2)}</span>
          <button class="btn-remove" onclick="removerDoCarrinho(${itemId})">Remover</button>
        </li>
      `;

      itensParaWhats.push({
        nome: prod.nome,
        quantidade: Number(item.quantidade || 0),
        valor_unitario: Number(prod.valor)
      });
    } else {
      // COMENTÁRIO: fallback seguro (não muda regras do sistema)
      // Se por algum motivo não achou o produto na lista, exibimos algo pra não parecer “vazio”
      html += `
        <li class="carrinho-item">
          <span>${Number(item.quantidade || 0)}x Produto #${itemId} (não carregado)</span>
          <span>—</span>
          <button class="btn-remove" onclick="removerDoCarrinho(${itemId})">Remover</button>
        </li>
      `;
    }
  });

  html += '</ul>';

  // Se o carrinho tem itens, mas NENHUM produto foi encontrado, avisamos:
  if (carrinho.length > 0 && !encontrouAlgumProduto) {
    html += `
      <p class="empty-cart">
        Não consegui carregar os dados dos produtos agora.
        Recarregue a página e tente novamente.
      </p>
    `;
  }

  // Total sempre aparece quando há itens, mesmo que 0 (transparência pro usuário)
  if (carrinho.length > 0) {
    html += `<h4 class="carrinho-total">Total: R$ ${total.toFixed(2)}</h4>`;
    html += `<button class="btn-primary carrinho-btn" onclick='enviarWhatsApp(${JSON.stringify(itensParaWhats)})'>Entrar em Contato</button>`;
  } else {
    html += '<p class="empty-cart">Seu carrinho está vazio.</p>';
  }

  // FIX: injeta APENAS no container correto do modal
  carrinhoItensEl.innerHTML = html;

  // Exibe modal
  const modal = document.getElementById('carrinhoModal');
  if (modal) {
    modal.style.display = 'flex';
  }
}

/**
 * Envia itens do carrinho para API e abre WhatsApp
 *
 * @param {array} itens - Lista de itens para WhatsApp
 */
async function enviarWhatsApp(itens) {
  try {
    const res = await fetch('/api/whatsapp', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(itens)
    });

    if (res.ok) {
      const data = await res.json();
      window.open(data.url, '_blank');

      // Limpa carrinho após envio
      localStorage.removeItem('carrinho');
      atualizarIconeCarrinho();
      fecharCarrinho();
    } else {
      alert('Erro ao gerar link. Tente novamente.');
    }
  } catch (error) {
    console.error('Erro:', error);
    alert('Erro de conexão. Verifique sua internet.');
  }
}

/**
 * Busca produtos na página
 */
function buscarProdutos() {
  const inputEl = document.getElementById('searchInput');
  const input = (inputEl ? inputEl.value : '').toLowerCase();
  const grid = document.getElementById('produtosGrid');

  if (!grid) return;

  const cards = grid.querySelectorAll('.card-produto');

  cards.forEach(card => {
    const title = card.querySelector('.card-title').textContent.toLowerCase();
    card.style.display = title.includes(input) ? 'block' : 'none';
  });
}

/**
 * Mostra notificação toast
 *
 * @param {string} mensagem - Mensagem a exibir
 */
function mostrarNotificacao(mensagem) {
  const notificacao = document.createElement('div');
  notificacao.className = 'notificacao';
  notificacao.textContent = mensagem;

  document.body.appendChild(notificacao);

  // Remove após 3 segundos
  setTimeout(() => {
    notificacao.style.animation = 'slideOut 0.3s ease';
    setTimeout(() => notificacao.remove(), 300);
  }, 3000);
}

/**
 * Fecha o modal ao clicar fora dele
 */
function fecharModalAoClicar(event) {
  const modal = document.getElementById('carrinhoModal');

  if (modal && event.target === modal) {
    fecharCarrinho();
  }
}

/**
 * Adiciona animações CSS dinamicamente
 */
function adicionarAnimacoes() {
  const style = document.createElement('style');
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
 * Inicializa o site ao carregar
 */
window.addEventListener('load', () => {
  carregarProdutos();
  atualizarIconeCarrinho();
  adicionarAnimacoes();

  const modal = document.getElementById('carrinhoModal');
  if (modal) {
    modal.addEventListener('click', fecharModalAoClicar);
  }

  const searchInput = document.getElementById('searchInput');
  if (searchInput) {
    searchInput.addEventListener('keypress', (e) => {
      if (e.key === 'Enter') buscarProdutos();
    });
  }

  console.log('✓ Site carregado com sucesso!');
});

/**
 * Sincroniza contagem do carrinho com outras abas
 */
setInterval(() => {
  atualizarIconeCarrinho();
}, 5000);

// ===== Mobile navigation =====
function toggleNavMenu() {
  const nav = document.getElementById('siteNav');
  if (!nav) return;
  nav.classList.toggle('open');
}

// Fecha menu se a tela for redimensionada para desktop
window.addEventListener('resize', () => {
  const nav = document.getElementById('siteNav');
  if (nav && window.innerWidth > 800) nav.classList.remove('open');
});
