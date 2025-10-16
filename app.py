import tkinter as tk
from tkinter import filedialog, messagebox
import sys
import os
import threading
import multiprocessing as mp
import re

# Tenta importar ttkbootstrap para um visual moderno
try:
    from ttkbootstrap import Style
    from ttkbootstrap.constants import *
    from ttkbootstrap.widgets import Frame, Button, Entry, Label, Spinbox, Progressbar
    Widget = sys.modules['ttkbootstrap.widgets']
    
except ImportError:
    from tkinter import ttk
    Widget = ttk
    
    class Style:
        Frame = Widget.Frame
        Button = Widget.Button
        Entry = Widget.Entry
        Spinbox = Widget.Spinbox
        Progressbar = Widget.Progressbar
        def __init__(self, theme): pass
        @property
        def master(self): return tk.Tk()

# Importa a função principal do seu outro script
try:
    from auto_vertical_crop import process_video
except ImportError:
    messagebox.showerror("Erro de Arquivo", "O arquivo 'auto_vertical_crop.py' não foi encontrado. Certifique-se de que ele está na mesma pasta.")
    sys.exit(1)

# --- Fila para comunicação de status entre processos ---
status_queue = mp.Queue()
processing_active = False

def worker_process(input_path, output_path, start, end, q):
    """
    @description Função alvo que roda no processo separado (isolado da GUI).
                 Roda a lógica principal do CLI.
    """
    # ⚠️ Ação: O stdout/stderr VAI para o terminal, como no CLI, para máxima estabilidade.
    
    try:
        # Executa o processamento do vídeo
        process_video(
            input_path=input_path,
            output_path=output_path,
            start=start,
            end=end,
            legenda="on"
        )
        q.put("SUCCESS:✅ Concluído! Vídeo salvo com sucesso.")
    except Exception as e:
        q.put(f"ERROR:❌ Erro no Processamento: {e}")
    finally:
        q.put("FINISHED")


def format_time_input(h_var, m_var, s_var):
    """
    @description Monta os valores dos Spinboxes no formato hh:mm:ss esperado pelo MoviePy.
    """
    try:
        h = int(h_var.get() or '0')
        m = int(m_var.get() or '0')
        s = int(s_var.get() or '0')
        
        if h == 0 and m == 0 and s == 0:
            return None
            
        return f"{h:02}:{m:02}:{s:02}"
    except ValueError:
        messagebox.showerror("Erro de Tempo", "O tempo de corte deve ser numérico (hh:mm:ss).")
        return "ERROR_INVALID_TIME"


def start_processing():
    """
    @description Inicia o processamento do vídeo em um processo separado.
    """
    global processing_active
    
    input_path = input_path_var.get()
    
    start_time_formatted = format_time_input(start_h_var, start_m_var, start_s_var)
    end_time_formatted = format_time_input(end_h_var, end_m_var, end_s_var)
    
    if start_time_formatted == "ERROR_INVALID_TIME" or end_time_formatted == "ERROR_INVALID_TIME":
        return
    
    if processing_active:
        messagebox.showwarning("Aviso", "O processamento já está em andamento.")
        return
    
    if not input_path:
        messagebox.showwarning("Aviso", "Por favor, selecione um arquivo de vídeo primeiro.")
        return

    output_path = filedialog.asksaveasfilename(
        title="Salvar vídeo como...",
        defaultextension=".mp4",
        filetypes=(("Vídeo MP4", "*.mp4"),)
    )

    if not output_path:
        status_var.set("Operação cancelada.")
        return

    processing_active = True
    process_button.config(state=tk.DISABLED)
    progress_bar.config(value=0, mode='indeterminate')
    progress_bar.start()
    status_var.set("⏳ Processando... Monitorando logs no terminal.")

    p = mp.Process(
        target=worker_process,
        args=(input_path, output_path, start_time_formatted, end_time_formatted, status_queue)
    )
    p.start()

    monitor_thread = threading.Thread(target=monitor_queue, args=(p,))
    monitor_thread.start()


def monitor_queue(process):
    """
    @description Monitora a fila de mensagens e atualiza a interface gráfica de forma segura.
    """
    global processing_active
    
    # Lista de mensagens de log esperadas (para atualizar o status da GUI)
    log_messages = [
        "Carregando Whisper (base)...",
        "Lendo o arquivo de vídeo...",
        "Gerando legendas automáticas com Whisper...",
        "Montando o vídeo final com áudio..."
    ]
    
    log_index = 0
    
    while True:
        if not status_queue.empty():
            message = status_queue.get()
            
            if message.startswith("SUCCESS:"):
                success_msg = message.replace("SUCCESS:", "")
                root.after(0, lambda: progress_bar.stop())
                root.after(0, lambda: progress_bar.config(value=100, mode='determinate'))
                root.after(0, lambda: status_var.set(success_msg))
                root.after(0, lambda: process_button.config(state=tk.NORMAL))
                root.after(0, lambda: messagebox.showinfo("Sucesso", "Renderização concluída!"))
                break
            
            elif message.startswith("ERROR:"):
                error_msg = message.replace("ERROR:", "")
                root.after(0, lambda: progress_bar.stop())
                root.after(0, lambda: progress_bar.config(value=0, mode='determinate'))
                root.after(0, lambda: status_var.set(error_msg))
                root.after(0, lambda: process_button.config(state=tk.NORMAL))
                root.after(0, lambda: messagebox.showerror("Erro de Processamento", error_msg))
                break
            
            elif message == "FINISHED":
                root.after(0, lambda: progress_bar.stop())
                root.after(0, lambda: process_button.config(state=tk.NORMAL))
                break
            
            else:
                # Log de status (Carregando Whisper, etc.)
                root.after(0, lambda: status_var.set(message))

        # Se o processo terminar por algum motivo (e.g., crash)
        if not process.is_alive():
            if status_var.get().startswith("⏳ Processando"):
                root.after(0, lambda: status_var.set("❌ Processo encerrado inesperadamente. Verifique o terminal para erros."))
            root.after(0, lambda: process_button.config(state=tk.NORMAL))
            root.after(0, lambda: progress_bar.stop())
            break
            
        root.update_idletasks()
        root.after(100)
    
    processing_active = False
    process.join()


def select_video_file():
    """
    @description Abre uma janela para o usuário selecionar o arquivo de vídeo.
    """
    filepath = filedialog.askopenfilename(
        title="1. Selecione o Arquivo de Vídeo",
        filetypes=(("Arquivos de Vídeo", "*.mp4 *.mov *.avi"), ("Todos os arquivos", "*.*"))
    )
    if filepath:
        input_path_var.set(filepath)
        display_path = "..." + filepath[-50:] if len(filepath) > 50 else filepath
        status_var.set(f"Arquivo selecionado: {display_path}")

if __name__ == '__main__':
    try:
        style = Style(theme='cosmo')
        root = style.master
    except NameError:
        root = tk.Tk()

    root.title("Auto Vertical Crop (Reels/Shorts)")
    root.geometry("550x380")
    root.resizable(False, False)

    # --- Variáveis de Controle do Tkinter ---
    input_path_var = tk.StringVar()
    # Variáveis dos Spinboxes
    start_h_var = tk.StringVar(value='00')
    start_m_var = tk.StringVar(value='00')
    start_s_var = tk.StringVar(value='00')
    end_h_var = tk.StringVar(value='00')
    end_m_var = tk.StringVar(value='00')
    end_s_var = tk.StringVar(value='00')
    status_var = tk.StringVar(value="Selecione um vídeo e defina os tempos de corte.")

    # --- Criação dos Widgets ---
    frame = Widget.Frame(root, padding="20")
    frame.pack(fill=tk.BOTH, expand=True)

    # Label de arquivo selecionado (para exibição)
    Widget.Label(frame, textvariable=status_var, wraplength=500, justify=tk.LEFT, font=('Helvetica', 10, 'bold')).pack(fill=tk.X, pady=(0, 10))
    
    # Barra de Progresso
    progress_bar = Widget.Progressbar(frame, orient=tk.HORIZONTAL, length=500, mode='indeterminate', bootstyle="info striped")
    progress_bar.pack(fill=tk.X, pady=(0, 15))


    # Linha 1: Seleção de arquivo
    select_button = Widget.Button(frame, text="1. SELECIONAR ARQUIVO DE VÍDEO", command=select_video_file, bootstyle="primary")
    select_button.pack(fill=tk.X, pady=10)

    # Linha 2: Título do bloco de tempo
    Widget.Label(frame, text="2. Tempos de Corte (hh:mm:ss, Opcional):", font=('Helvetica', 10, 'bold')).pack(fill=tk.X, anchor=tk.W, pady=(5, 5))

    # Frame para conter os campos de tempo (GRID)
    time_grid_frame = Widget.Frame(frame)
    time_grid_frame.pack(fill=tk.X, pady=(0, 10))

    # --- Campo de INÍCIO (Start) ---
    Widget.Label(time_grid_frame, text="Início:").grid(row=0, column=0, sticky=tk.W, padx=(0, 10))
    
    # Spinboxes de Início
    start_h_spin = Widget.Spinbox(time_grid_frame, from_=0, to=99, textvariable=start_h_var, width=4, justify=tk.CENTER)
    start_m_spin = Widget.Spinbox(time_grid_frame, from_=0, to=59, textvariable=start_m_var, width=4, justify=tk.CENTER)
    start_s_spin = Widget.Spinbox(time_grid_frame, from_=0, to=59, textvariable=start_s_var, width=4, justify=tk.CENTER)

    start_h_spin.grid(row=0, column=1, sticky=tk.W)
    Widget.Label(time_grid_frame, text="h").grid(row=0, column=2, sticky=tk.W, padx=(2, 10))
    start_m_spin.grid(row=0, column=3, sticky=tk.W)
    Widget.Label(time_grid_frame, text="m").grid(row=0, column=4, sticky=tk.W, padx=(2, 10))
    start_s_spin.grid(row=0, column=5, sticky=tk.W)
    Widget.Label(time_grid_frame, text="s").grid(row=0, column=6, sticky=tk.W, padx=(2, 10))


    # --- Campo de FIM (End) ---
    Widget.Label(time_grid_frame, text="Fim:").grid(row=1, column=0, sticky=tk.W, padx=(0, 10), pady=(10, 0))
    
    # Spinboxes de Fim
    end_h_spin = Widget.Spinbox(time_grid_frame, from_=0, to=99, textvariable=end_h_var, width=4, justify=tk.CENTER)
    end_m_spin = Widget.Spinbox(time_grid_frame, from_=0, to=59, textvariable=end_m_var, width=4, justify=tk.CENTER)
    end_s_spin = Widget.Spinbox(time_grid_frame, from_=0, to=59, textvariable=end_s_var, width=4, justify=tk.CENTER)

    end_h_spin.grid(row=1, column=1, sticky=tk.W, pady=(10, 0))
    Widget.Label(time_grid_frame, text="h").grid(row=1, column=2, sticky=tk.W, padx=(2, 10), pady=(10, 0))
    end_m_spin.grid(row=1, column=3, sticky=tk.W, pady=(10, 0))
    Widget.Label(time_grid_frame, text="m").grid(row=1, column=4, sticky=tk.W, padx=(2, 10), pady=(10, 0))
    end_s_spin.grid(row=1, column=5, sticky=tk.W, pady=(10, 0))
    Widget.Label(time_grid_frame, text="s").grid(row=1, column=6, sticky=tk.W, padx=(2, 10), pady=(10, 0))
    
    time_grid_frame.columnconfigure(7, weight=1)
    
    # Linha 3: Botão de Processar
    process_button = Widget.Button(frame, text="3. PROCESSAR E SALVAR (Com Legendas)", command=start_processing, bootstyle="success")
    process_button.pack(fill=tk.X, pady=(15, 0))

    # --- Iniciar a Interface Gráfica ---
    root.mainloop()