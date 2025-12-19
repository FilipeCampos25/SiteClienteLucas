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
    // Incrementa quantidade
    existente.quantidade += 1;
  } else {
    // Adiciona novo item
    carrinho.push({ id: id, quantidade: 1 });
  }
  
  // Salva no localStorage
  localStorage.setItem('carrinho', JSON.stringify(carrinho));
  
  // Atualiza o ícone do carrinho
  atualizarIconeCarrinho();
  
  // Feedback visual ao usuário
  mostrarNotificacao('✓ Produto adicionado ao carrinho!');
}

/**
 * Abre o modal do carrinho com todos os itens
 * Calcula o total e prepara dados para WhatsApp
 */
function abrirCarrinho() {
  let carrinho = JSON.parse(localStorage.getItem('carrinho') || '[]');
  
  // Inicia o HTML do modal
  let html = '<div class="modal-content">';
  html += '<span class="close-modal" onclick="fecharCarrinho()">&times;</span>';
  html += '<h3>🛒 Seu Carrinho</h3><ul>';
  
  let total = 0;
  const itensParaWhats = [];
  
  // Itera sobre os itens do carrinho
  carrinho.forEach(item => {
    const prod = (window.todosProdutos || []).find(p => p.id === item.id);
    
    if (prod) {
      const subtotal = parseFloat(prod.valor) * item.quantidade;
      total += subtotal;
      
      // Adiciona item ao HTML
      html += `
        <li>
          <div>
            <strong>${item.quantidade}x</strong> ${prod.nome}
            <br>
            <span style="color: #FF6200; font-weight: 600;">R$ ${subtotal.toFixed(2)}</span>
          </div>
          <button onclick="remover(${item.id})" title="Remover do carrinho">✕</button>
        </li>
      `;
      
      // Prepara dados para WhatsApp
      itensParaWhats.push({
        nome: prod.nome,
        quantidade: item.quantidade,
        valor_unitario: Number(prod.valor)
      });
    }
  });
  
  html += `</ul>`;
  
  // Adiciona total
  html += `
    <div style="background: #F8F8F8; padding: 1rem; border-radius: 8px; margin: 1rem 0;">
      <h4 style="margin: 0; color: #FF6200;">Total: R$ ${total.toFixed(2)}</h4>
    </div>
  `;
  
  // Adiciona botão de ação
  if (carrinho.length > 0) {
    html += `
      <button 
        onclick='enviarWhats(${JSON.stringify(itensParaWhats)})' 
        class="btn-submit"
        style="width: 100%; margin-top: 1rem;"
      >
        💬 Enviar via WhatsApp
      </button>
    `;
  } else {
    html += '<p style="text-align: center; color: #999; margin-top: 1rem;">Carrinho vazio</p>';
  }
  
  html += '</div>';
  
  // Exibe o modal
  const modal = document.getElementById('carrinhoModal');
  modal.innerHTML = html;
  modal.style.display = 'flex';
}

/**
 * Remove um produto do carrinho
 * 
 * @param {number} id - ID do produto a remover
 */
function remover(id) {
  let carrinho = JSON.parse(localStorage.getItem('carrinho') || '[]');
  
  // Filtra removendo o produto
  carrinho = carrinho.filter(i => i.id !== id);
  
  // Salva no localStorage
  localStorage.setItem('carrinho', JSON.stringify(carrinho));
  
  // Atualiza ícone e modal
  atualizarIconeCarrinho();
  abrirCarrinho();
  
  mostrarNotificacao('✓ Produto removido do carrinho');
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
 * Envia os itens do carrinho via WhatsApp
 * Chama a API de geração de link do WhatsApp
 * 
 * @param {array} itens - Array com os itens do carrinho
 */
async function enviarWhats(itens) {
  try {
    // Envia os itens para a API
    const res = await fetch('/api/whatsapp', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(itens)
    });
    
    if (res.ok) {
      const data = await res.json();
      
      // Abre o link do WhatsApp em nova aba
      window.open(data.url, '_blank');
      
      // Limpa o carrinho após envio
      localStorage.removeItem('carrinho');
      atualizarIconeCarrinho();
      fecharCarrinho();
      
      mostrarNotificacao('✓ Redirecionando para WhatsApp...');
    } else {
      alert("Erro ao gerar link do WhatsApp. Tente novamente.");
    }
  } catch (error) {
    console.error("Erro:", error);
    alert("Erro ao conectar com o servidor.");
  }
}

/**
 * Busca produtos por nome
 * Filtra os produtos carregados e exibe os resultados
 */
function buscarProdutos() {
  const searchInput = document.getElementById('searchInput');
  
  if (!searchInput) return;
  
  const termo = searchInput.value.toLowerCase().trim();
  
  if (termo === '') {
    // Se vazio, recarrega a página
    location.reload();
    return;
  }
  
  // Filtra produtos que contêm o termo
  const resultados = todosProdutos.filter(p => 
    p.nome.toLowerCase().includes(termo) || 
    (p.descricao && p.descricao.toLowerCase().includes(termo))
  );
  
  // Atualiza o grid de produtos
  atualizarGridProdutos(resultados);
}

/**
 * Atualiza o grid de produtos com novos resultados
 * 
 * @param {array} produtos - Array com os produtos a exibir
 */
function atualizarGridProdutos(produtos) {
  const gridProdutos = document.querySelector('.grid-produtos');
  
  if (!gridProdutos) return;
  
  if (produtos.length === 0) {
    gridProdutos.innerHTML = `
      <div class="empty-state" style="grid-column: 1 / -1;">
        <p class="empty-state-text">Nenhum produto encontrado.</p>
      </div>
    `;
    return;
  }
  
  // Reconstrói o grid com os produtos filtrados
  gridProdutos.innerHTML = produtos.map(p => `
    <div class="card-produto">
      <div class="card-image-wrapper">
        <img 
          src="${p.imagem_url}" 
          alt="${p.nome}" 
          class="card-image" 
          onerror="this.src='/static/images/placeholder.png'"
        >
        <span class="product-badge">Novo</span>
      </div>
      <div class="card-body">
        <h3 class="product-name">${p.nome}</h3>
        <div class="price-section">
          <span class="product-price">R$ ${parseFloat(p.valor).toFixed(2)}</span>
        </div>
        ${p.descricao ? `<p class="product-description">${p.descricao.substring(0, 80)}...</p>` : ''}
        <div class="card-actions">
          <button 
            class="btn-adicionar" 
            onclick="adicionarCarrinho(${p.id})"
          >
            Adicionar
          </button>
          <a href="/produto/${p.id}" class="btn-detalhes">
            Detalhes
          </a>
        </div>
      </div>
    </div>
  `).join('');
}

/**
 * Mostra uma notificação temporária ao usuário
 * 
 * @param {string} mensagem - Mensagem a exibir
 */
function mostrarNotificacao(mensagem) {
  // Cria elemento de notificação
  const notificacao = document.createElement('div');
  notificacao.textContent = mensagem;
  notificacao.style.cssText = `
    position: fixed;
    bottom: 20px;
    right: 20px;
    background: #FF6200;
    color: white;
    padding: 12px 20px;
    border-radius: 8px;
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.2);
    z-index: 999;
    animation: slideIn 0.3s ease;
    font-weight: 600;
  `;
  
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
