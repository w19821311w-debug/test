const state = {
    gens: 0,
    words: 0,
    myChart: null
};

function showTab(tabId, element) {
    document.querySelectorAll('.tab-content').forEach(tab => tab.classList.remove('active'));
    document.querySelectorAll('.nav-item').forEach(item => item.classList.remove('active'));

    document.getElementById('tab-' + tabId).classList.add('active');
    element.classList.add('active');

    if (tabId === 'analytics') {
        setTimeout(initChart, 200);
    }
}

document.getElementById('genBtn').onclick = async () => {
    const btn = document.getElementById('genBtn');
    const output = document.getElementById('outputContainer');
    
    const name = document.getElementById('pName').value;
    const market = document.getElementById('pMarket').value;
    const features = document.getElementById('pFeatures').value;

    if (!name || !features) {
        alert("Заполните поля!");
        return;
    }

    btn.innerText = "Создаем...";
    btn.disabled = true;
    output.innerHTML = `<div class="loading-text">Интеллект работает...</div>`;

    try {
        const response = await fetch('http://127.0.0.1:8000/generate-description', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ name, marketplace: market, features })
        });

        const data = await response.json();
        output.innerHTML = `<div class="ai-content fade-in">${marked.parse(data.description)}</div>`;
        
        state.gens++;
        state.words += data.description.split(/\s+/).length;
        updateStats();

    } catch (err) {
        output.innerHTML = `<p style="color: #FF7276">Ошибка связи. Проверь сервер!</p>`;
    } finally {
        btn.innerText = "Сгенерировать";
        btn.disabled = false;
    }
};

function copyContent() {
    const text = document.getElementById('outputContainer').innerText;
    navigator.clipboard.writeText(text).then(() => {
        const btn = document.getElementById('copyBtn');
        btn.innerText = "Скопировано!";
        setTimeout(() => btn.innerText = "Копировать", 2000);
    });
}

function updateStats() {
    document.getElementById('stat-gen').innerText = state.gens;
    document.getElementById('stat-words').innerText = state.words;
}

function initChart() {
    const ctx = document.getElementById('usageChart').getContext('2d');
    if (state.myChart) state.myChart.destroy();
    state.myChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс'],
            datasets: [{
                data: [0, 0, 0, 0, 0, 0, state.gens],
                borderColor: '#FF7276',
                tension: 0.4,
                fill: true,
                backgroundColor: 'rgba(255, 114, 118, 0.1)'
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: { legend: { display: false } },
            scales: { y: { display: false }, x: { grid: { display: false } } }
        }
    });
}