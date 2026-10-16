# Passo a Passo Desktop

App desktop que transforma os cliques do usuário em tutoriais passo a passo: cada clique vira uma captura de tela com um círculo vermelho no local clicado e o texto "Passo N: clique aqui".

Este é o **protótipo da fase 0** (somente Windows 10/11). O plano completo está em [docs/PLANO_TECNICO.md](docs/PLANO_TECNICO.md).

## O que já funciona

- Barra flutuante (sem borda, sempre no topo, arrastável) com Iniciar, Pausar/Retomar, Finalizar, contador de passos e cronômetro.
- Contagem regressiva de 3 segundos antes de gravar.
- Atalhos globais: **Ctrl+Shift+F9** pausa ou retoma, **Ctrl+Shift+F10** finaliza.
- Um passo por clique, capturado no botão pressionado, no monitor onde o clique aconteceu.
- Texto automático com o elemento clicado (UI Automation): "Clique no botão Salvar no Bloco de Notas", "Abra o menu Arquivo", "Clique na aba ... no Google Chrome". Campos de senha aparecem só como "campo de senha".
- Duplo clique vira um passo só; clique direito tem texto próprio.
- **Tab** e **Enter** também viram passos ("Pressione Enter no ...", "Pressione Tab 3 vezes"), capturados no key-down. Tabs seguidos ou segurados viram um passo só; com Ctrl, Alt ou Win são ignorados. Nada do que é digitado é gravado. Liga e desliga na engrenagem (ligado por padrão).
- Programas que rodam como administrador (comum em sistemas legados, como os feitos em COBOL): o Windows não entrega os cliques deles a um app comum. A barra avisa e oferece **Reiniciar como administrador** (também na engrenagem). Cliques e teclas descartados ficam registrados em `%LOCALAPPDATA%\PassoAPasso\erros.log`.
- Fundo desfocado e escurecido, com o local do clique nítido (configurável no tema).
- Cliques na barra são ignorados e a barra não aparece nas capturas.
- DPI Per-Monitor V2, para o círculo cair no lugar certo em telas com 125%, 150% etc.
- Projeto salvo numa pasta temporária a cada passo e, ao finalizar, em um arquivo `.passo` onde você escolher.
- Janela de revisão: miniaturas, captura com o círculo, título e texto do passo editáveis.
- Ordem dos passos: setas ▲ ▼ abaixo das miniaturas (ou Ctrl+↑/↓ na lista) e campo **Posição** para levar o passo direto a outro número (de 1 até o total). Os textos "Passo N:" são renumerados e Ctrl+Z desfaz.
- Painel **Aparência**: logo (PNG, JPG ou SVG, copiada para dentro do `.passo`), cores do destaque, das margens, do fundo da página e do texto (com aviso de pouco contraste), e o tipo de destaque do fundo.
- **Exportar…**: PDF (A4 ou Carta, 1 ou 2 passos por página, capa, selo numerado, círculo em vetor), GIF animado (960 px, 12 quadros/s, repetição infinita) e vídeo MP4 (1080p ou 720p, 30 quadros/s), com zoom suave no clique, círculo com pulso e transição esmaecer, deslizar ou zoom. Roda em segundo plano, com barra de progresso e Cancelar.

Edição do círculo, reordenar e excluir passos, desfoque de dados sensíveis e desfazer ficam para a próxima fase.

## Como instalar

Requer Windows 10 (versão 2004 ou mais nova) ou 11 e Python 3.12 ou mais novo.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## Como rodar

Dê dois cliques no atalho **Passo a Passo** da Área de Trabalho (abre sem console). Ele chama `.venv\Scripts\pythonw.exe "Passo a Passo.pyw"`; erros vão para `%LOCALAPPDATA%\PassoAPasso\erros.log`.

Pelo terminal:

```powershell
python -m app
```

1. Clique em **Iniciar** e espere a contagem de 3 segundos.
2. Use o computador normalmente; cada clique vira um passo.
3. Clique em **Finalizar** (ou Ctrl+Shift+F10) e escolha onde salvar o `.passo`.
4. Revise os passos e edite os textos; **Salvar** (ou Ctrl+S) grava as alterações.

## Como ver um tutorial salvo

- Pela barra: **Abrir tutorial** e escolha o `.passo`.
- Pelo terminal: `python -m app caminho\tutorial.passo`.

Na revisão, **Salvar imagens** grava numa pasta um PNG por passo (`passo-001.png`, ...), com o círculo e o texto numa faixa embaixo. É uma prévia simples; PDF, vídeo e GIF chegam na fase 2.

## Testes

```powershell
python -m pytest
```

## Gerar o executável

```powershell
pip install pyinstaller
pyinstaller packaging\PassoAPasso.spec --noconfirm
```

A build sai em `dist\Passo a Passo\` (pasta inteira; o `.exe` sozinho não roda) com Python, Qt, FFmpeg e os wrappers do UI Automation embutidos. Para conferir sem abrir janelas:

```powershell
$env:QT_QPA_PLATFORM = "offscreen"
Start-Process "dist\Passo a Passo\Passo a Passo.exe" -ArgumentList "--autoteste", "--relatorio=$env:TEMP\autoteste.txt" -Wait -PassThru
```

Código de saída 0 e `AUTOTESTE OK` no relatório indicam que imports, janelas e exportação de PDF, GIF e MP4 funcionam. Para distribuir, compacte a pasta junto com `packaging\LEIA-ME.txt`.

## Estrutura

| Pasta | Conteúdo |
| --- | --- |
| `app/ui` | Barra de gravação e janela de revisão |
| `app/recorder` | Controlador, máquina de estados, worker de captura e atalhos globais |
| `app/capture` | Interfaces `InputHook` e `ScreenGrabber`, adaptador Windows (pynput + mss) e conversão de coordenadas |
| `app/project` | Modelo de dados e leitura/escrita do `.passo` |
| `app/render` | Desenho do círculo de destaque com Pillow |
| `tests` | Testes pytest |

## Formato `.passo`

ZIP com `project.json` (schema 1, descrito no plano técnico) e as capturas originais em `images/`, sem anotação. O círculo é desenhado só na hora de exibir ou exportar.
