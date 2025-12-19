// Carrinho cliente (localStorage) — carrega todos produtos de /api/produtos uma vez
let todosProdutos = [];

async function carregarProdutos() {
  if (todosProdutos.length > 0) return; // Simples cache
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
  }
}

function atualizarIconeCarrinho() {
  const carrinho = JSON.parse(localStorage.getItem('carrinho') || '[]');
  const totalItens = carrinho.reduce((sum, item) => sum + item.quantidade, 0);
  const cartBtn = document.querySelector('.cart-btn');
  cartBtn.setAttribute('data-count', totalItens);
  if (totalItens > 0) {
    cartBtn.classList.add('has-items');
  } else {
    cartBtn.classList.remove('has-items');
  }
}

function adicionarCarrinho(id) {
  let carrinho = JSON.parse(localStorage.getItem('carrinho') || '[]');
  const existente = carrinho.find(i => i.id === id);
  if (existente) existente.quantidade += 1;
  else carrinho.push({id: id, quantidade: 1});
  localStorage.setItem('carrinho', JSON.stringify(carrinho));
  atualizarIconeCarrinho();
  alert('Adicionado ao carrinho!');
}

function abrirCarrinho() {
  let carrinho = JSON.parse(localStorage.getItem('carrinho') || '[]');
  let html = '<span class="close-modal" onclick="fecharCarrinho()">&times;</span>'; // Adicionado close
  html += '<h3>Seu Carrinho</h3><ul>';
  let total = 0;
  const itensParaWhats = [];
  carrinho.forEach(item => {
    const prod = (window.todosProdutos || []).find(p => p.id === item.id);
    if (prod) {
      const subtotal = parseFloat(prod.valor) * item.quantidade;
      total += subtotal;
      html += `<li>${item.quantidade}x ${prod.nome} - R$ ${subtotal.toFixed(2)} <button onclick="remover(${item.id})">X</button></li>`;
      itensParaWhats.push({nome: prod.nome, quantidade: item.quantidade, valor_unitario: Number(prod.valor)});
    }
  });
  html += `</ul><h4>Total: R$ ${total.toFixed(2)}</h4>`;
  if (carrinho.length > 0) {
    html += `<button onclick='enviarWhats(${JSON.stringify(itensParaWhats)})' class="btn-laranja">Entrar em contato</button>`;
  } else {
    html += '<p>Carrinho vazio.</p>';
  }
  const modal = document.getElementById('carrinhoModal');
  modal.innerHTML = html;
  modal.style.display = 'block';
}

function remover(id) {
  let carrinho = JSON.parse(localStorage.getItem('carrinho') || '[]');
  carrinho = carrinho.filter(i => i.id !== id);
  localStorage.setItem('carrinho', JSON.stringify(carrinho));
  atualizarIconeCarrinho();
  abrirCarrinho(); // Recarrega modal
}

function fecharCarrinho() {
  document.getElementById('carrinhoModal').style.display = 'none';
}

async function enviarWhats(itens) {
  try {
    const res = await fetch('/api/whatsapp', {
      method: 'POST',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify(itens)
    });
    if (res.ok) {
      const data = await res.json();
      window.open(data.url, '_blank');
      localStorage.removeItem('carrinho'); // Limpa carrinho após envio
      atualizarIconeCarrinho();
      fecharCarrinho();
    } else {
      alert("Erro ao gerar link do WhatsApp.");
    }
  } catch (error) {
    console.error("Erro:", error);
  }
}

window.addEventListener('load', () => {
  carregarProdutos();
  atualizarIconeCarrinho();
});