function criarGrafico() {
  const canvas = document.getElementById('meuGrafico');

  if (canvas instanceof HTMLCanvasElement) {
    let contexto = canvas.getContext('2d');

    // @ts-ignore
    let grafico = new Chart(contexto, {
      type: 'bar', //pie
      data: {
        //labels: ["Argentina", "Brasil", "Chile"],
        labels: [],
        datasets: [
          {
            label: 'Quantidade',
            //data: [3, 20, 9],
            data: [],
            borderWidth: 1,
            //backgroundColor: ["#fcff32ff", "#34e758ff", " #ba66f5ff"],
            backgroundColor: [],
          },
        ],
      },
      options: {
        plugins: {
          legend: {
            labels: {
              font: { size: 20 },
              color: '#697b6dff',
              boxWidth: 0,
            },
          },
        },

        scales: {
          x: {
            ticks: { font: { size: 18 }, color: '#697b6dff' },
          },
          y: {
            ticks: { font: { size: 18 }, color: '#697b6dff' },
            beginAtZero: true,
          },
        },
      },
    });
    conectarWebSocket(grafico);
  }
}
// @ts-ignore
function conectarWebSocket(grafico) {
  let socket = new WebSocket('ws://192.168.1.102:8080');
  socket.onmessage = (event) => {
    try {
      let dados = JSON.parse(event.data);
      processamentoMensagem(grafico, dados);
    } catch (erro) {
      console.error('Falha ao processar a mensagem'), erro;
    }

    socket.onclose = () => {
      setTimeout(() => conectarWebSocket(grafico), 2000);
    };
  };
}

// @ts-ignore
function processamentoMensagem(grafico, dados) {
  console.log(dados);
  let indiceTipo = grafico.data.labels.indexOf(dados.tipo);
  console.log(indiceTipo);
  if (indiceTipo === -1) {
    console.log(dados.tipo);
    console.log(dados.quantidade);
    grafico.data.labels.push(dados.tipo);
    grafico.data.datasets[0].data.push(dados.quantidade);
    grafico.data.datasets[0].backgroundColor.push(corPorTipo(dados.tipo));
  } else {
    grafico.data.datasets[0].data[indiceTipo] = dados.quantidade;
  }
  grafico.update();
}

// @ts-ignore
function corPorTipo(tipo) {
  switch (tipo) {
    case 'Grande':
      return '#fcff32ff';
    case 'Media':
      return '#34e758ff';
    case 'Pequena':
      return '#ba66f5ff';
    default:
      return;
  }
}

document.addEventListener('DOMContentLoaded', criarGrafico);
