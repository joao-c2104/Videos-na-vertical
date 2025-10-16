# Videos-na-vertical

Transforma vídeos horizontais em verticais (proporção 9:16 para Reels/Shorts/TikTok), dando zoom inteligente em rostos, com legendas automáticas opcionais e delimitação de corte.

## 🚀 Como Usar: Guia de Instalação e Execução 

O programa pode ser executado via uma interface gráfica simples (`app.py`) ou diretamente pela linha de comando (`auto_vertical_crop.py`).

### 1. Preparação do Ambiente

1.  **Estrutura da Pasta:** Coloque os arquivos `auto_vertical_crop.py`, `app.py`, e `requirements.txt` na pasta principal do seu projeto. Certifique-se de que a subpasta `src/fonts` contém o arquivo **`arial.ttf`**.

2.  **Abra o Terminal** (ou **Prompt de Comando/PowerShell** no Windows) na pasta do projeto.

3.  **Crie e Ative o Ambiente Virtual (VENV):**

    ```bash
    # 1. Cria o ambiente virtual
    python -m venv venv

    # 2. Ative o ambiente virtual
    # No Windows:
    .\venv\Scripts\activate
    # No macOS/Linux:
    source venv/bin/activate
    ```

4.  **Instale as Dependências (Pacotes Python):**

    ```bash
    pip install -r requirements.txt
    ```

5.  **Instalações Específicas de SO (CRUCIAL):**
    * **macOS (Homebrew):** Para a GUI funcionar, você precisa do pacote `tkinter` separado:
        ```bash
        brew install python-tk@3.11
        ```
    * **Windows / Linux:** Não é necessário instalar nada extra aqui. O `pip install` já é suficiente.

### 2. Execução do Programa

#### Opção A (Recomendada): Execução via Interface Gráfica (GUI)

Esta é a forma mais fácil de usar, com validação de tempo e salvamento fácil.

1.  **Certifique-se que o VENV está ativo.**

2.  **Execute o aplicativo:**

    ```bash
    python app.py
    ```

3.  **Na Janela:**
    * **1. SELECIONAR ARQUIVO DE VÍDEO:** Abre a janela do sistema para escolher o vídeo.
    * **2. Tempos de Corte:** Use as caixas de **`Spinbox`** (setinhas) para definir o corte exato em `hh:mm:ss`. Se deixado em `00:00:00`, o programa processa o vídeo inteiro.
    * **Checkbox:** Use o checkbox para **Ligar ou Desligar** as legendas automáticas.
    * **3. PROCESSAR E SALVAR:** Abre a janela "Salvar como..." para definir o nome e o local do vídeo final.

#### Opção B: Execução via Linha de Comando (CLI)

Use para automação ou testes diretos.

1.  **Certifique-se que o VENV está ativo.**

2.  **Execute o comando:**

    ```bash
    python auto_vertical_crop.py --input XX.mp4 --output XX_vertical.mp4 --start hh:mm:ss --end hh:mm:ss --out_h 1080 --legenda on
    ```

    | Parâmetro | Descrição | Exemplo |
    | :--- | :--- | :--- |
    | `--input` | Caminho do vídeo de entrada. | `video3.mp4` |
    | `--output` | Caminho do vídeo final. | `video_final.mp4` |
    | `--start` | Tempo de início do corte (Opcional). | `00:00:15` |
    | `--end` | Tempo de fim do corte (Opcional). | `00:00:45` |
    | `--legenda` | Liga (`on`) ou Desliga (`off`) a legenda. | `off` |

---

### ⚠️ Limite de Duração para Mídias Sociais

O programa aplica um limite máximo de **60 segundos** para o corte total do vídeo, o que é o limite ideal para Reels, Shorts e TikTok, garantindo que seu conteúdo seja aceito em todas as plataformas.