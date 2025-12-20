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
  const totalItens = carrinho.reduce((sum, item) => sum + item.quantidade, 0);
  
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
  let carrinho = JSON.parse(localStorage.getItem('carrinho') || '[]');
  
  // Verifica se o produto já está no carrinho
  const existente = carrinho.find(i => i.id === id);
  
  if (existente) {
    existente.quantidade++;
  } else {
    carrinho.push({id, quantidade: 1});
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
  let carrinho = JSON.parse(localStorage.getItem('carrinho') || '[]');
  
  const index = carrinho.findIndex(i => i.id === id);
  
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
  let html = '<h3 class="modal-title">Seu Carrinho</h3><ul class="carrinho-lista">';
  let total = 0;
  const itensParaWhats = [];

  carrinho.forEach(item => {
    const prod = todosProdutos.find(p => p.id === item.id);
    if (prod) {
      const subtotal = prod.valor * item.quantidade;
      total += subtotal;
      html += `
        <li class="carrinho-item">
          <span>${item.quantidade}x ${prod.nome}</span>
          <span>R$ ${subtotal.toFixed(2)}</span>
          <button class="btn-remove" onclick="removerDoCarrinho(${item.id})">Remover</button>
        </li>
      `;
      itensParaWhats.push({
        nome: prod.nome,
        quantidade: item.quantidade,
        valor_unitario: prod.valor
      });
    }
  });

  html += '</ul>';
  html += `<h4 class="carrinho-total">Total: R$ ${total.toFixed(2)}</h4>`;
  
  if (carrinho.length > 0) {
    html += `<button class="btn-primary carrinho-btn" onclick='enviarWhatsApp(${JSON.stringify(itensParaWhats)})'>Entrar em Contato</button>`;
  } else {
    html += '<p class="empty-cart">Seu carrinho está vazio.</p>';
  }

  const modalContent = document.querySelector('#carrinhoModal .modal-content');
  if (modalContent) {
    modalContent.innerHTML = html;
  }

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
  const input = document.getElementById('searchInput').value.toLowerCase();
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
      from {
        transform: translateX(400px);
        opacity: 0;
      }
      to {
        transform: translateX(0);
        opacity: 1;
      }
    }
    
    @keyframes slideOut {
      from {
        transform: translateX(0);
        opacity: 1;
      }
      to {
        transform: translateX(400px);
        opacity: 0;
      }
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
 * Carrega produtos, atualiza carrinho e adiciona event listeners
 */
window.addEventListener('load', () => {
  // Carrega produtos
  carregarProdutos();
  
  // Atualiza ícone do carrinho
  atualizarIconeCarrinho();
  
  // Adiciona animações
  adicionarAnimacoes();
  
  // Event listener para fechar modal ao clicar fora
  const modal = document.getElementById('carrinhoModal');
  if (modal) {
    modal.addEventListener('click', fecharModalAoClicar);
  }
  
  // Event listener para busca ao pressionar Enter
  const searchInput = document.getElementById('searchInput');
  if (searchInput) {
    searchInput.addEventListener('keypress', (e) => {
      if (e.key === 'Enter') {
        buscarProdutos();
      }
    });
  }
  
  console.log('✓ Site carregado com sucesso!');
});

/**
 * Atualiza o carrinho a cada 5 segundos (sincronização com outras abas)
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