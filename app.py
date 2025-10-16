# app.py (corrigido)
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

# --- Variáveis globais (serão inicializadas no main) ---
status_queue = None
processing_active = False

def worker_process(input_path, output_path, start, end, legenda, q):
    """
    Função que roda no processo separado (isolado da GUI).
    Recebe q (queue) para enviar status de volta.
    """
    try:
        q.put("Iniciando processamento...")
        process_video(
            input_path=input_path,
            output_path=output_path,
            out_h=1080,
            legenda=legenda,
            start=start,
            end=end
        )
        q.put("SUCCESS:✅ Concluído! Vídeo salvo com sucesso.")
    except Exception as e:
        q.put(f"ERROR:❌ Erro no Processamento: {e}")
    finally:
        q.put("FINISHED")

def time_to_seconds_from_vars(h_var, m_var, s_var):
    """
    Converte valores das Spinboxes (strings) em segundos.
    Retorna um inteiro >=0, ou None se todos zeros.
    Lança ValueError se inválido.
    """
    try:
        h = int(h_var.get() or "0")
        m = int(m_var.get() or "0")
        s = int(s_var.get() or "0")
    except Exception as e:
        raise ValueError("Valores de tempo devem ser numéricos")

    if h < 0 or m < 0 or s < 0 or m > 59 or s > 59:
        raise ValueError("Minutos/segundos fora do intervalo (0-59)")

    seconds = h * 3600 + m * 60 + s
    return seconds if seconds > 0 else 0

def format_time_input(h_var, m_var, s_var):
    """
    Retorna string 'HH:MM:SS' ou None se zero.
    Lança ValueError em caso de entrada inválida.
    """
    seconds = time_to_seconds_from_vars(h_var, m_var, s_var)
    if seconds == 0:
        return None
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    return f"{h:02d}:{m:02d}:{s:02d}"

def start_processing():
    """
    Inicia o processamento em um processo separado e monitora via fila.
    """
    global processing_active, status_queue

    input_path = input_path_var.get()
    if not input_path or not os.path.exists(input_path):
        messagebox.showwarning("Aviso", "Por favor, selecione um arquivo de vídeo válido primeiro.")
        return

    try:
        start_str = format_time_input(start_h_var, start_m_var, start_s_var)
        end_str = format_time_input(end_h_var, end_m_var, end_s_var)
    except ValueError as ve:
        messagebox.showerror("Erro de Entrada", str(ve))
        return

    # Validação simples: se ambos informados e end <= start -> erro
    if start_str and end_str:
        def to_secs(t):
            if t is None: return None
            parts = [int(x) for x in t.split(":")]
            return parts[0]*3600 + parts[1]*60 + parts[2]
        if to_secs(end_str) <= to_secs(start_str):
            messagebox.showerror("Erro de Tempo", "O tempo final deve ser maior que o tempo inicial.")
            return
        # (opcional) limite de duração
        MAX_DURATION_SECONDS = 60
        if (to_secs(end_str) - to_secs(start_str)) > MAX_DURATION_SECONDS:
            messagebox.showerror("Limite de Duração", f"O corte excede o limite de {MAX_DURATION_SECONDS} segundos.")
            return

    if processing_active:
        messagebox.showwarning("Aviso", "O processamento já está em andamento.")
        return

    output_path = filedialog.asksaveasfilename(title="Salvar vídeo como...", defaultextension=".mp4",
                                               filetypes=(("Vídeo MP4", "*.mp4"),))
    if not output_path:
        status_var.set("Operação cancelada.")
        return

    legenda_status = "on" if legenda_var.get() == 1 else "off"

    # Criar Manager e Queue aqui (evita problemas no Windows)
    manager = mp.Manager()
    status_queue = manager.Queue()

    processing_active = True
    process_button.config(state=tk.DISABLED)
    progress_bar.config(value=0, mode='indeterminate')
    progress_bar.start()
    status_var.set("⏳ Processando... (veja o terminal para logs detalhados)")

    # Cria e inicia o processo
    p = mp.Process(target=worker_process,
                   args=(input_path, output_path, start_str, end_str, legenda_status, status_queue),
                   daemon=True)
    p.start()

    monitor_thread = threading.Thread(target=monitor_queue, args=(p,), daemon=True)
    monitor_thread.start()

def monitor_queue(process):
    """
    Monitora a fila de mensagens e atualiza a GUI.
    """
    global processing_active, status_queue

    while True:
        try:
            # espera por mensagens por até 0.1s para não travar
            if status_queue is not None and not status_queue.empty():
                message = status_queue.get()

                # tenta extrair progresso (caso MoviePy envie)
                prog_match = re.search(r'(\d+)%', message)
                if prog_match:
                    try:
                        percentage = int(prog_match.group(1))
                        root.after(0, lambda: progress_bar.stop())
                        root.after(0, lambda: progress_bar.config(mode='determinate', value=percentage, maximum=100))
                        root.after(0, lambda: status_var.set(f"Renderizando... {percentage}% concluído"))
                    except Exception:
                        pass

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
                    # mostra último trecho da mensagem
                    short = message if len(message) <= 200 else message[-200:]
                    root.after(0, lambda s=short: status_var.set(s))

            if not process.is_alive():
                # se morreu sem colocar mensagem, reporta erro
                if status_var.get().startswith("⏳ Processando"):
                    root.after(0, lambda: status_var.set("❌ Processo encerrado inesperadamente. Verifique o terminal."))
                root.after(0, lambda: process_button.config(state=tk.NORMAL))
                root.after(0, lambda: progress_bar.stop())
                break

            # evita loop muito apertado
            root.update_idletasks()
            mp.time.sleep(0.1)

        except Exception as e:
            # log local (mas não quebra o loop)
            print("Erro no monitor_queue:", e)
            break

    processing_active = False
    try:
        process.join(timeout=0.1)
    except Exception:
        pass

def select_video_file():
    filepath = filedialog.askopenfilename(title="1. Selecione o Arquivo de Vídeo",
                                          filetypes=(("Arquivos de Vídeo", "*.mp4 *.mov *.avi"), ("Todos", "*.*")))
    if filepath:
        input_path_var.set(filepath)
        display_path = ("..." + filepath[-50:]) if len(filepath) > 50 else filepath
        status_var.set(f"Arquivo selecionado: {display_path}")

# -------------------- Construção da GUI --------------------
if __name__ == '__main__':
    try:
        style = Style(theme='cosmo')
        root = style.master
    except NameError:
        root = tk.Tk()

    root.title("Auto Vertical Crop (Reels/Shorts)")
    root.geometry("640x480")
    root.resizable(False, False)

    # Variáveis
    input_path_var = tk.StringVar()
    start_h_var = tk.StringVar(value='00')
    start_m_var = tk.StringVar(value='00')
    start_s_var = tk.StringVar(value='00')
    end_h_var = tk.StringVar(value='00')
    end_m_var = tk.StringVar(value='00')
    end_s_var = tk.StringVar(value='00')
    legenda_var = tk.IntVar(value=1)
    status_var = tk.StringVar(value="Selecione um vídeo e defina os tempos de corte.")

    frame = Widget.Frame(root, padding="12")
    frame.pack(fill=tk.BOTH, expand=True)

    Widget.Label(frame, textvariable=status_var, wraplength=600, justify=tk.LEFT, font=('Helvetica', 10, 'bold')).pack(fill=tk.X, pady=(0, 10))
    progress_bar = Widget.Progressbar(frame, orient=tk.HORIZONTAL, length=600, mode='indeterminate', bootstyle="info striped")
    progress_bar.pack(fill=tk.X, pady=(0, 12))

    select_button = Widget.Button(frame, text="1. SELECIONAR ARQUIVO DE VÍDEO", command=select_video_file, bootstyle="primary")
    select_button.pack(fill=tk.X, pady=8)

    Widget.Label(frame, text="2. Tempos de Corte (hh:mm:ss, Opcional):", font=('Helvetica', 10, 'bold')).pack(fill=tk.X, anchor=tk.W, pady=(6,4))
    time_grid_frame = Widget.Frame(frame)
    time_grid_frame.pack(fill=tk.X, pady=(0,8))

    Widget.Label(time_grid_frame, text="Início:").grid(row=0, column=0, sticky=tk.W, padx=(0,10))
    start_h_spin = Widget.Spinbox(time_grid_frame, from_=0, to=99, textvariable=start_h_var, width=4)
    start_m_spin = Widget.Spinbox(time_grid_frame, from_=0, to=59, textvariable=start_m_var, width=4)
    start_s_spin = Widget.Spinbox(time_grid_frame, from_=0, to=59, textvariable=start_s_var, width=4)
    start_h_spin.grid(row=0, column=1)
    Widget.Label(time_grid_frame, text="h").grid(row=0, column=2, padx=(2,10))
    start_m_spin.grid(row=0, column=3)
    Widget.Label(time_grid_frame, text="m").grid(row=0, column=4, padx=(2,10))
    start_s_spin.grid(row=0, column=5)
    Widget.Label(time_grid_frame, text="s").grid(row=0, column=6, padx=(2,10))

    Widget.Label(time_grid_frame, text="Fim:").grid(row=1, column=0, sticky=tk.W, padx=(0,10), pady=(6,0))
    end_h_spin = Widget.Spinbox(time_grid_frame, from_=0, to=99, textvariable=end_h_var, width=4)
    end_m_spin = Widget.Spinbox(time_grid_frame, from_=0, to=59, textvariable=end_m_var, width=4)
    end_s_spin = Widget.Spinbox(time_grid_frame, from_=0, to=59, textvariable=end_s_var, width=4)
    end_h_spin.grid(row=1, column=1, pady=(6,0))
    Widget.Label(time_grid_frame, text="h").grid(row=1, column=2, padx=(2,10), pady=(6,0))
    end_m_spin.grid(row=1, column=3, pady=(6,0))
    Widget.Label(time_grid_frame, text="m").grid(row=1, column=4, padx=(2,10), pady=(6,0))
    end_s_spin.grid(row=1, column=5, pady=(6,0))
    Widget.Label(time_grid_frame, text="s").grid(row=1, column=6, padx=(2,10), pady=(6,0))

    legenda_checkbox = Widget.Checkbutton(frame, text="Incluir Legendas Automáticas", variable=legenda_var)
    legenda_checkbox.pack(fill=tk.X, anchor=tk.W, pady=(8,6))

    process_button = Widget.Button(frame, text="3. PROCESSAR E SALVAR (Com Legendas)", command=start_processing, bootstyle="success")
    process_button.pack(fill=tk.X, pady=(10,0))

    root.mainloop()
