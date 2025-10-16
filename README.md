# Videos-na-vertical

Transforma vídeos horizontais em verticais (proporção 9:16 para Reels/Shorts/TikTok), dando zoom inteligente em rostos, com legendas automáticas opcionais e delimitação de corte.

## 📄 Descrição do Projeto

O **Videos-na-vertical** transforma vídeos horizontais em verticais, ideais para **Reels, Shorts e TikTok**.

  * Recorte automático inteligente, focando em rostos com **MediaPipe FaceMesh**.
  * Legendas automáticas opcionais via **OpenAI Whisper**.
  * Ajuste de legenda automático para caber no vídeo sem cortar linhas.
  * Mantém o conteúdo vertical sem esticar ou distorcer.
  * Interface gráfica amigável (GUI) e suporte a linha de comando (CLI).

## 🔧 Pré-requisitos

  * **Python 3.10+** (recomendado)
  * Bibliotecas Python:
    ```
    pip install moviepy opencv-python pillow mediapipe openai-whisper numpy ttkbootstrap
    ```
  * **FFmpeg** instalado ou presente na mesma pasta do script.
    ```
    ffmpeg -version
    ```
  * Sistema operacional compatível: Windows, Linux e macOS.

## 📂 Estrutura de Pastas Recomendada

```
Videos-na-vertical/
├─ auto_vertical_crop.py
├─ app.py
├─ requirements.txt
├─ README.md
├─ src/
│  └─ fonts/
│     └─ arial.ttf
```

## 🚀 Como Usar: Guia de Instalação e Execução

O programa pode ser executado via **GUI (app.py)** ou diretamente pela **linha de comando (auto\_vertical\_crop.py)**.

### 1\. Preparação do Ambiente

1.  Abra o terminal (ou **Prompt de Comando/PowerShell** no Windows) na pasta do projeto.
2.  Crie e ative o ambiente virtual (VENV):
    ```
    python -m venv venv

    # Ative o ambiente virtual
    # No Windows:
    .\venv\Scripts\activate
    # No macOS/Linux:
    source venv/bin/activate
    ```
3.  Instale as dependências:
    ```
    pip install -r requirements.txt
    ```
4.  Certifique-se de que o arquivo `arial.ttf` está dentro de `src/fonts`.

### 2\. Execução do Programa

#### Opção A (GUI - Recomendada)

1.  Certifique-se que o VENV está ativo.
2.  Execute:
    ```
    python app.py
    ```
3.  Na Janela:
      * **1. SELECIONAR ARQUIVO DE VÍDEO:** Escolha o vídeo desejado.
      * **2. Tempos de Corte:** Defina início e fim em `hh:mm:ss`. Se deixado em 00:00:00, processa todo o vídeo.
      * **Checkbox:** Ligue ou desligue legendas automáticas.
      * **3. PROCESSAR E SALVAR:** Escolha onde salvar o vídeo final.

#### Opção B (Linha de Comando - CLI)

1.  Certifique-se que o VENV está ativo.
2.  Execute:
    ```
    python auto_vertical_crop.py --input XX.mp4 --output XX_vertical.mp4 --start hh:mm:ss --end hh:mm:ss --out_h 1080 --legenda on
    ```

| Parâmetro | Descrição | Exemplo |
| :--- | :--- | :--- |
| --input | Caminho do vídeo de entrada. | video3.mp4 |
| --output | Caminho do vídeo final. | video\_final.mp4 |
| --start | Tempo de início do corte (Opcional). | 00:00:15 |
| --end | Tempo de fim do corte (Opcional). | 00:00:45 |
| --legenda | Liga (on) ou desliga (off) a legenda. | off |

### ⚠️ Limite de Duração

O corte total recomendado é até **60 segundos** para Reels, Shorts e TikTok.
