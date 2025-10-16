import tkinter as tk
from tkinter import filedialog, messagebox
import sys
import os
import threading
import multiprocessing as mp
import re

try:
    from ttkbootstrap import Style
    from ttkbootstrap.constants import *
    from ttkbootstrap.widgets import Frame, Button, Entry, Label, Spinbox, Progressbar, Checkbutton
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
        Checkbutton = Widget.Checkbutton
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

def worker_process(input_path, output_path, start, end, legenda, q):
    """
    @description Função alvo que roda no processo separado (isolado da GUI).
    """
    
    try:
        process_video(
            input_path=input_path,
            output_path=output_path,
            start=start,
            end=end,
            legenda=legenda
        )
        q.put("SUCCESS:✅ Concluído! Vídeo salvo com sucesso.")
    except Exception as e:
        q.put(f"ERROR:❌ Erro no Processamento: {e}")
    finally:
        q.put("FINISHED")


def time_to_seconds(h_var, m_var, s_var):
    """
    @description Converte hh:mm:ss em segundos.
    """
    try:
        h = int(h_var.get() or '0')
        m = int(m_var.get() or '0')
        s = int(s_var.get() or '0')
        
        if h < 0 or m < 0 or s < 0 or m > 59 or s > 59:
             raise ValueError("Tempo inválido")
        
        return h * 3600 + m * 60 + s
    except ValueError:
        return "ERROR_INVALID_TIME"


def format_time_input(h_var, m_var, s_var):
    """
    @description Monta os valores dos Spinboxes no formato hh:mm:ss esperado pelo MoviePy.
    """
    seconds = time_to_seconds(h_var, m_var, s_var)
    if seconds == "ERROR_INVALID_TIME":
        return "ERROR_INVALID_TIME"
        
    if seconds == 0:
        return None
        
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    return f"{h:02}:{m:02}:{s:02}"


def start_processing():
    """
    @description Inicia o processamento do vídeo em um processo separado.
    """
    global processing_active
    
    input_path = input_path_var.get()
    
    start_sec = time_to_seconds(start_h_var, start_m_var, start_s_var)
    end_sec = time_to_seconds(end_h_var, end_m_var, end_s_var)
    
    if start_sec == "ERROR_INVALID_TIME" or end_sec == "ERROR_INVALID_TIME":
        messagebox.showerror("Erro de Entrada", "Por favor, insira valores numéricos válidos (0-59 para minutos/segundos).")
        return
    
    # ⚠️ VALIDAÇÃO DE LIMITE DE DURAÇÃO (60 SEGUNDOS)
    if start_sec is not None and end_sec is not None and end_sec > start_sec:
        duration = end_sec - start_sec
        MAX_DURATION_SECONDS = 60
        if duration > MAX_DURATION_SECONDS:
            messagebox.showerror("Limite de Duração", f"O corte solicitado ({duration}s) excede o limite de {MAX_DURATION_SECONDS} segundos para vídeos curtos.")
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

    # Obtém o status da legenda (on/off)
    legenda_status = "on" if legenda_var.get() == 1 else "off"
    
    processing_active = True
    process_button.config(state=tk.DISABLED)
    progress_bar.config(value=0, mode='indeterminate')
    progress_bar.start()
    status_var.set("⏳ Processando... Monitorando logs no terminal.")

    p = mp.Process(
        target=worker_process,
        args=(input_path, output_path, 
              format_time_input(start_h_var, start_m_var, start_s_var), 
              format_time_input(end_h_var, end_m_var, end_s_var), 
              legenda_status, status_queue)
    )
    p.start()

    monitor_thread = threading.Thread(target=monitor_queue, args=(p,))
    monitor_thread.start()


def monitor_queue(process):
    """
    @description Monitora a fila de mensagens e atualiza a interface gráfica de forma segura.
    """
    global processing_active
    
    while True:
        if not status_queue.empty():
            message = status_queue.get()
            
            # Tenta capturar o progresso do MoviePy
            progress_match = re.search(r't:\s*(\d+)%', message)
            
            if progress_match:
                percentage = int(progress_match.group(1))
                root.after(0, lambda: progress_bar.stop())
                root.after(0, lambda: progress_bar.config(mode='determinate', value=percentage, maximum=100))
                root.after(0, lambda: status_var.set(f"Renderizando... {percentage}% concluído"))
            
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
            
            elif not progress_match:
                root.after(0, lambda: status_var.set(message[-100:]))

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
    root.geometry("550x420")
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
    legenda_var = tk.IntVar(value=1) # 1 = Ligado por padrão
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
    
    # Checkbox de Legenda (Removido o bootstyle="toggle" problemático)
    legenda_checkbox = Widget.Checkbutton(frame, 
                                          text="Incluir Legendas Automáticas", 
                                          variable=legenda_var)
    legenda_checkbox.pack(fill=tk.X, anchor=tk.W, pady=(10, 5))


    # Linha 3: Botão de Processar
    process_button = Widget.Button(frame, text="3. PROCESSAR E SALVAR (Com Legendas)", command=start_processing, bootstyle="success")
    process_button.pack(fill=tk.X, pady=(15, 0))

    # --- Iniciar a Interface Gráfica ---
    root.mainloop()