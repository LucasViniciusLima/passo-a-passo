# Plano técnico: Passo a Passo Desktop

2 de outubro de 2026 · Lucas Bezerra

## Resumo

A proposta é um app desktop em Python com interface PySide6 (Qt 6), rodando em Windows 10/11 e Linux (Fedora e Ubuntu), gratuito e de uso pessoal, que grava cada clique como um passo com captura de tela e círculo vermelho, permite revisar e exporta para PDF, MP4 e GIF com a identidade visual do usuário.

O plano prioriza um núcleo de captura confiável no Windows e no Linux antes da edição e da exportação, porque é ali que estão as diferenças de permissão, de escala de tela (HiDPI) e de Wayland, que é o padrão no Fedora e no Ubuntu.

**Escopo do MVP**

- Gravação com Iniciar, Pausar, Retomar e Finalizar, por botões e atalhos globais.
- Um passo por clique: captura da tela, posição do clique e texto padrão "Passo N: clique aqui".
- Revisão: reordenar, excluir, editar texto, mover ou redimensionar o círculo, desfocar áreas sensíveis.
- Exportação para PDF, vídeo MP4 e GIF animado com transições suaves.
- Marca: logo selecionável e substituível, cores do destaque, das margens e do fundo da página.

**Fora do MVP**

- Texto automático com o nome do botão clicado ("Clique em Salvar"), que depende das APIs de acessibilidade de cada sistema.
- Captura de digitação, narração por voz, nuvem e colaboração.

## Stack tecnológica

Todas as bibliotecas abaixo são maduras, gratuitas e com licenças compatíveis com um app de código aberto (MIT, BSD, LGPL ou GPL).

| Camada | Escolha | Por quê | Alternativa |
| --- | --- | --- | --- |
| Linguagem | Python 3.12 | Pedido do usuário; suporte longo e wheels disponíveis | Python 3.13 |
| Interface | PySide6 (Qt 6) | Nativa no Windows e no Linux, LGPL, QGraphicsScene serve de canvas de edição, janelas sem borda e sempre no topo para a barra de gravação | PyQt6 |
| Clique e atalhos no Windows e X11 | pynput | Hooks globais de mouse e teclado com uma só API | Hooks nativos via ctypes |
| Clique no Wayland | python-evdev | Lê os eventos do mouse direto do kernel, o único caminho fora do compositor | libinput via ctypes |
| Tela no Windows e X11 | mss | Rápida (10 a 30 ms), múltiplos monitores, sem dependências | Pillow ImageGrab |
| Tela e cursor no Wayland | Portal XDG ScreenCast + GStreamer (PyGObject) | Caminho oficial do GNOME e do KDE para captura contínua com posição do cursor | libpipewire via ctypes |
| Imagem | Pillow + NumPy | Composição, recorte, desfoque e geração de quadros | OpenCV (mais pesado) |
| PDF | ReportLab | Desenho vetorial: o círculo e os textos saem nítidos em qualquer zoom | WeasyPrint |
| Vídeo e GIF | FFmpeg via imageio-ffmpeg | Binário pronto; quadros enviados por pipe, sem arquivos temporários | PyAV |
| Configurações | platformdirs + JSON | Pasta correta de configuração em cada sistema | QSettings |
| Empacotamento | PyInstaller (Windows), nfpm (.deb e .rpm) | Instaladores nativos de cada sistema | Briefcase |
| Testes | pytest + pytest-qt | Testes de modelo, exportadores e interface | unittest |

## Arquitetura e módulos

Três camadas independentes conversam apenas pelo projeto `.passo`: a gravação escreve passos, o editor altera o projeto e os exportadores só leem dele.

```
Gravação:    Barra de gravação -> Controlador (máquina de estados) -> Hook de entrada (pynput) -> Worker de captura (mss)
                                                                                                  |
Projeto:                         Editor de revisão  <---------------------------->  Projeto .passo (project.json + PNGs + tema)
                                                                                                  |
Exportação:  PDF (ReportLab) <------------------- Anotações (círculo e selo) -> Linha do tempo -> FFmpeg (MP4 e GIF)
```

O hook roda na sua própria thread e apenas enfileira eventos; a captura acontece num worker, e a interface Qt recebe atualizações por sinais, então nenhuma etapa pesada trava o clique do usuário.

| Pacote Python | Responsabilidade |
| --- | --- |
| `app/ui` | Telas Qt: início, barra de gravação, editor, diálogo de exportação |
| `app/recorder` | Controlador e máquina de estados da gravação, atalhos globais |
| `app/capture` | Interface `InputHook` e `ScreenGrabber` com adaptadores por sistema |
| `app/project` | Modelo de dados, leitura e escrita do `.passo`, migrações |
| `app/render` | Anotações (círculo, selo, desfoque) e linha do tempo de quadros |
| `app/export` | Exportadores PDF, MP4 e GIF, com progresso e cancelamento |
| `app/theme` | Tema, predefinições, logo e cores |

## Captura de cliques e telas por sistema

Windows 10/11 é o caminho simples; Fedora e Ubuntu são o desafio, porque ambos usam Wayland por padrão e as versões recentes removeram a sessão X11 do GNOME, então o suporte a Wayland entra no MVP com um adaptador próprio.

| Sistema | Clique | Captura de tela e posição | Permissões | Cuidado principal |
| --- | --- | --- | --- | --- |
| Windows 10/11 | pynput (hook WH\_MOUSE\_LL) | mss (GDI) | Nenhuma | Declarar DPI por monitor (Per-Monitor V2), senão o clique cai no lugar errado em telas com escala de 125% ou 150% |
| Fedora e Ubuntu com Wayland | python-evdev lendo só os dispositivos de mouse | Portal XDG ScreenCast: stream PipeWire lido via GStreamer, com a posição do cursor nos metadados | Uma regra udev instalada pelo pacote para ler o mouse; o usuário autoriza o compartilhamento de tela uma vez, e o app guarda a autorização (restore token) | Wayland não dá a posição global do cursor a apps comuns; ela só vem pelos metadados do ScreenCast |
| Ubuntu e Fedora com X11 (quando houver) | pynput (Xlib/XRecord) | mss (XGetImage) | Nenhuma | Escala fracionária |

O app detecta a sessão pela variável `XDG_SESSION_TYPE` e escolhe o adaptador. O Windows vem primeiro; no início do porte para Linux há um protótipo curto para confirmar que o GStreamer entrega os metadados do cursor; se não entregar, o plano B é um pequeno módulo que lê o stream PipeWire direto pela libpipewire via ctypes.

**Fluxo de um clique**

1. O adaptador recebe o evento de botão pressionado (não o de soltar), para capturar a tela antes que a interface clicada mude.
2. O evento vai para uma fila com posição, botão, hora e monitor; o hook nunca faz trabalho pesado.
3. Um worker pega a imagem: no Windows tira a captura com mss; no Wayland usa o quadro mais recente do stream, que já está rodando.
4. O worker converte a posição para pixels da imagem, salva o PNG original sem anotação e registra o passo; a interface recebe um sinal Qt e atualiza o contador.

**Regras de filtragem e janela de controle**

- Cliques na própria barra de gravação são ignorados, comparando a posição com o retângulo da janela.
- A barra fica fora das capturas: no Windows com SetWindowDisplayAffinity; no Linux ela é recortada da imagem pela posição conhecida ou escondida durante a captura.
- No Wayland, apps comuns não conseguem ficar sempre no topo; a interface roda via XWayland (`QT_QPA_PLATFORM=xcb`), onde o GNOME e o KDE respeitam esse pedido.
- Atalhos globais: no Windows via pynput; no Wayland pelo portal GlobalShortcuts quando o ambiente oferecer, e só pelos botões da barra quando não oferecer. Padrão Ctrl+Shift+F9 pausa ou retoma, Ctrl+Shift+F10 finaliza.
- Duplo clique vira um único passo "Clique duas vezes"; arrastar vira "Arraste daqui até ali".
- Contagem regressiva de 3 segundos antes de começar a gravar.

## Modelo de dados e formato de projeto

Cada tutorial é salvo como um arquivo `.passo`, que é um ZIP com um `project.json` e as capturas originais; anotações nunca são gravadas nos pixels, então trocar cor, logo ou posição do círculo não exige regravar.

```
meu-tutorial.passo (ZIP)
├── project.json
├── images/step-001.png   (captura original)
├── images/step-002.png
└── assets/logo.png
```

```json
{
  "schema": 1,
  "title": "Como emitir uma nota",
  "created_at": "2026-10-02T13:30:00Z",
  "theme": {
    "logo": "assets/logo.png",
    "highlight_color": "#E53935",
    "margin_color": "#FFFFFF",
    "page_background": "#F5F5F5",
    "text_color": "#212121",
    "circle": {"radius": 28, "stroke": 4, "fill_opacity": 0.15}
  },
  "steps": [
    {
      "id": "8f1c",
      "image": "images/step-001.png",
      "action": "click",
      "button": "left",
      "point": [812, 440],
      "end_point": null,
      "monitor": 1,
      "scale": 1.5,
      "timestamp": 1.84,
      "text": "Passo 1: clique aqui",
      "circle_override": null,
      "crop": null,
      "blur_regions": []
    }
  ]
}
```

- A ordem dos passos é a ordem do array; o número exibido é calculado na exportação, então reordenar renumera sozinho.
- `schema` permite migrar arquivos antigos quando o formato mudar.
- Durante a gravação o projeto vive numa pasta temporária e é salvo a cada passo, para não perder nada se o app fechar.

## Interface: gravação, revisão e edição

O app tem três telas: início, barra flutuante de gravação e editor de revisão; a exportação abre como janela de diálogo a partir do editor.

| Tela | O que tem | Detalhes técnicos |
| --- | --- | --- |
| Início | Novo tutorial, abrir recente, configurações e temas | Lista de recentes em platformdirs |
| Barra de gravação | Iniciar, Pausar/Retomar, Finalizar, contador de passos, cronômetro | Janela pequena, sem borda, sempre no topo, arrastável; a janela principal minimiza ao gravar |
| Editor de revisão | Miniaturas à esquerda, captura grande ao centro, texto do passo abaixo, painel de tema à direita | QGraphicsScene com o círculo como item arrastável e redimensionável |
| Exportar | Formato, tamanho, duração por passo, transição, prévia | Roda em QThread com barra de progresso e Cancelar |

**Estados da gravação**

Ocioso, Gravando, Pausado e Finalizado. Em Pausado o hook continua ativo mas descarta eventos, para retomar sem atraso. Finalizar fecha a barra e abre o editor com os passos gravados.

**Ações no editor**

- Reordenar por arrastar, excluir, duplicar e inserir uma captura nova entre passos.
- Editar o texto do passo; o padrão "Passo N: clique aqui" muda conforme a ação (clique, duplo clique, clique direito, arrastar).
- Mover e redimensionar o círculo, ou trocar por seta ou retângulo em um passo específico.
- Recortar ou dar zoom numa área, e desfocar regiões com dados sensíveis (senhas, e-mails, CPF).
- Desfazer e refazer com QUndoStack; salvamento automático.

A interface sai em português do Brasil, com textos em arquivos de tradução do Qt para incluir outros idiomas depois.

## Exportação: PDF, vídeo e GIF

O PDF é desenhado em vetor pelo ReportLab; vídeo e GIF compartilham um único renderizador de linha do tempo que gera quadros com Pillow e os envia ao FFmpeg por pipe.

**PDF (ReportLab)**

- Capa com logo, título, data e número de passos.
- Um ou dois passos por página, A4 ou Carta, retrato ou paisagem.
- Cada passo: selo com o número na cor de destaque, texto, captura com margem colorida; o círculo é desenhado em vetor sobre a imagem, nítido em qualquer zoom.
- Cabeçalho com logo e rodapé com número da página; fundo da página na cor do tema.
- Imagens comprimidas em JPEG de qualidade alta ou PNG, conforme a opção de tamanho do arquivo.

**Renderizador de linha do tempo (compartilhado)**

Para cada passo ele monta uma sequência: entrada com transição, zoom suave em direção ao clique, círculo surgindo com um pulso, legenda com o texto do passo, tempo de leitura e saída. Transições disponíveis: esmaecer (crossfade), deslizar e zoom. Abertura e encerramento opcionais com o logo.

| Formato | Codificação | Padrão | Opções |
| --- | --- | --- | --- |
| Vídeo | MP4 H.264, FFmpeg | 1920x1080, 30 fps, 3 s por passo, transição de 0,5 s | 720p ou 4K, duração por passo, tipo de transição, WebM como alternativa sem H.264 |
| GIF | FFmpeg em duas passadas (palettegen e paletteuse) | 960 px de largura, 12 fps, repetição infinita | Largura, fps, número de cores; aviso quando passar de um tamanho-alvo |

O GIF usa paleta otimizada pelo FFmpeg porque o Pillow sozinho gera faixas de cor visíveis nas transições. Toda exportação roda fora da thread da interface, mostra progresso e pode ser cancelada.

## Identidade visual: logo e cores

A marca é um objeto Tema salvo dentro de cada projeto e também como predefinição reutilizável, aplicado igualmente ao PDF, ao vídeo e ao GIF.

| Item | Padrão | Onde aparece |
| --- | --- | --- |
| Logo (PNG, JPG ou SVG) | Nenhum | Capa e cabeçalho do PDF, abertura e canto do vídeo e do GIF |
| Cor do destaque | Vermelho #E53935 | Círculo, selo do número do passo |
| Cor das margens | Branco #FFFFFF | Moldura em volta de cada captura |
| Cor de fundo da página | Cinza claro #F5F5F5 | Fundo das páginas do PDF e dos quadros do vídeo |
| Cor do texto | Cinza escuro #212121 | Textos dos passos e legendas |
| Estilo do círculo | Raio 28 px, borda 4 px, preenchimento 15% | Todas as capturas, com ajuste por passo no editor |

- Selecionar ou substituir a logo copia o arquivo para dentro do `.passo`, então o projeto continua íntegro se o original for apagado.
- Cores escolhidas com QColorDialog, com prévia ao vivo no editor.
- Aviso quando o texto ficar com pouco contraste sobre o fundo escolhido.
- Predefinições salvas na pasta de configuração do usuário, para aplicar a mesma marca em todos os tutoriais com um clique.

## Empacotamento e distribuição

O usuário final instala um app normal, sem configurar Python; os pacotes são gerados no GitHub Actions, cada um no próprio sistema, e publicados nas Releases do repositório.

| Sistema | Pacote | Como é montado | Observação |
| --- | --- | --- | --- |
| Windows 10/11 | Instalador Inno Setup (.exe) | PyInstaller com Python, Qt e FFmpeg embutidos | Sem assinatura de código (uso pessoal), o SmartScreen avisa na primeira execução |
| Ubuntu | .deb | App num ambiente Python próprio, GStreamer e PyGObject do sistema como dependências do pacote | Instala a regra udev que libera a leitura do mouse |
| Fedora | .rpm | Mesmo esquema do .deb, gerado com nfpm | Idem |

No Linux o GStreamer e o plugin do PipeWire vêm do sistema, porque embuti-los no pacote costuma quebrar entre versões da distribuição. Flatpak fica fora: o sandbox impede ler o mouse via evdev.

**Licença**

O projeto é pessoal, público no GitHub e sem distribuição no mercado, então não há licença a escolher, e o FFmpeg padrão com libx264 serve.

Tamanho estimado do instalador Windows: de 120 a 180 MB, a maior parte do Qt e do FFmpeg.

## Testes, riscos e roadmap

O app nasce no Windows: o protótipo valida a captura lá, revisão e exportação vêm em seguida, e o porte para Fedora e Ubuntu entra depois. A camada de captura usa interfaces desde o início, então o porte troca só os adaptadores, sem mexer no resto.

**Testes**

- Unitários (pytest): modelo de dados, migração de schema, conversão de coordenadas por escala e monitor.
- Imagens de referência: o renderizador de anotações e os quadros do vídeo comparados pixel a pixel com imagens aprovadas.
- Exportadores: número de páginas do PDF, duração e resolução do MP4 via ffprobe, tamanho e quadros do GIF.
- Interface (pytest-qt): estados da gravação e ações do editor.
- Captura real: roteiro manual antes de cada versão em Windows 10, Windows 11, Fedora e Ubuntu (máquinas virtuais servem), com GNOME e KDE no Linux.

**Riscos**

| Risco | Impacto | Mitigação |
| --- | --- | --- |
| Wayland não expõe a posição global do cursor | Sem gravação no Fedora e no Ubuntu | Metadados do portal ScreenCast; protótipo no início do porte para Linux; plano B lendo o PipeWire direto |
| Ler o mouse via evdev exige permissão extra | Usuário desconfia ou a instalação falha | Regra udev só para dispositivos de mouse, explicada na instalação; o teclado nunca é lido no Linux |
| Barra de gravação some atrás de outras janelas no Wayland | Usuário não acha o botão de parar | Interface via XWayland; atalhos pelo portal GlobalShortcuts; ícone na bandeja |
| Coordenadas erradas em HiDPI e múltiplos monitores | Círculo fora do lugar | DPI por monitor no Windows, escala do stream no Wayland, testes com 100%, 150% e 200% |
| Tela muda entre o clique e a captura | Captura mostra o estado errado | Capturar no botão pressionado; no Wayland usar o quadro anterior ao clique |
| Dados sensíveis nas capturas | Vazamento de senha ou dados pessoais | Ferramenta de desfoque, pausa por atalho, nenhum envio para a internet |
| Antivírus marcando hook de teclado | Instalação bloqueada no Windows | Exceção no antivírus para uso pessoal; ouvir o teclado apenas para os atalhos |

**Roadmap**

| Fase | Entregas | Passa quando |
| --- | --- | --- |
| 0. Protótipo Windows | Captura de cliques com círculo vermelho (pynput e mss); barra Iniciar, Pausar, Retomar, Finalizar; projeto .passo salvo | 50 cliques corretos no Windows 10/11, com HiDPI e 2 monitores |
| 1. Revisão | Editor com miniaturas, textos e círculo editável; reordenar, desfoque, desfazer e refazer | Um tutorial de 20 passos é editado e reaberto sem perda |
| 2. Exportação e marca | PDF, MP4 e GIF com transições suaves; logo, cores e predefinições de tema | O mesmo projeto exporta nos 3 formatos (versão Windows completa) |
| 3. Porte para Linux | Captura no Wayland (evdev e portal ScreenCast); pacotes .deb e .rpm, testes em GNOME e KDE | Gravar, revisar e exportar funcionam no Fedora e no Ubuntu |
| 4. Evolução | Texto automático com o nome do botão clicado; outros ambientes Linux, atualização automática | — |

Cada fase só começa quando a anterior cumpre seu critério; a fase 0 valida a captura no Windows antes de qualquer trabalho de edição ou exportação.

**Decisões em aberto**

- Versões mínimas: o plano assume Ubuntu 22.04 LTS e Fedora 40 ou mais novos, além de Windows 10 e 11.
- Ambientes Linux: o plano testa GNOME e KDE; outros (XFCE, Cinnamon) ficam como melhor esforço.

---

Versão editável: https://claude.ai/code/artifact/dc9dc38b-7c02-4378-bb5a-00219779170e
