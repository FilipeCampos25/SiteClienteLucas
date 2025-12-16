// Carrinho cliente (localStorage) — carrega todos produtos de /api/produtos uma vez
let todosProdutos = [];

async function carregarProdutos(){
  const res = await fetch('/api/produtos');
  if(res.ok){
    todosProdutos = await res.json();
    window.todosProdutos = todosProdutos;
  } else {
    console.error("Erro carregando produtos");
  }
}

function atualizarIconeCarrinho(){ /* placeholder */ }

function adicionarCarrinho(id){
  let carrinho = JSON.parse(localStorage.getItem('carrinho') || '[]');
  const existente = carrinho.find(i => i.id === id);
  if(existente) existente.quantidade += 1;
  else carrinho.push({id: id, quantidade: 1});
  localStorage.setItem('carrinho', JSON.stringify(carrinho));
  alert('Adicionado ao carrinho');
}

function abrirCarrinho(){
  let carrinho = JSON.parse(localStorage.getItem('carrinho') || '[]');
  let html = '<h3>Seu Carrinho</h3><ul>';
  let total = 0;
  const itensParaWhats = [];
  carrinho.forEach(item => {
    const prod = (window.todosProdutos || []).find(p => p.id === item.id);
    if(prod){
      const subtotal = parseFloat(prod.valor) * item.quantidade;
      total += subtotal;
      html += `<li>${item.quantidade}x ${prod.nome} - R$ ${subtotal.toFixed(2)} <button onclick="remover(${item.id})">X</button></li>`;
      itensParaWhats.push({nome: prod.nome, quantidade: item.quantidade, valor_unitario: Number(prod.valor)});
    }
  });
  html += `</ul><h4>Total: R$ ${total.toFixed(2)}</h4>`;
  html += `<button onclick="enviarWhats(${JSON.stringify(itensParaWhats)})" class="btn-laranja">Entrar em contato</button>`;
  const modal = document.getElementById('carrinhoModal');
  modal.innerHTML = html;
  modal.style.display = 'block';
}

function remover(id){
  let carrinho = JSON.parse(localStorage.getItem('carrinho') || '[]');
  carrinho = carrinho.filter(i => i.id !== id);
  localStorage.setItem('carrinho', JSON.stringify(carrinho));
  abrirCarrinho();
}

async function enviarWhats(itens){
  const res = await fetch('/api/whatsapp', {
    method: 'POST',
    headers: {'Content-Type':'application/json'},
    body: JSON.stringify(itens)
  });
  const data = await res.json();
  window.open(data.url, '_blank');
}

window.addEventListener('load', carregarProdutos);
