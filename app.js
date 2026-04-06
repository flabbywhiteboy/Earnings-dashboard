const list = document.getElementById("cardList");

function render() {
  list.innerHTML = stocks.map(s => `
    <div class="stock-card ${s.status}">
      <strong>${s.company}</strong> (${s.ticker}) - ${s.status}
    </div>
  `).join("");
}
render();