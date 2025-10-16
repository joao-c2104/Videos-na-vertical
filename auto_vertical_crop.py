# auto_vertical_crop.py (corrigido)
import sys
import os
import tempfile
import argparse
import numpy as np

try:
    import cv2
    import mediapipe as mp
    from moviepy.editor import VideoFileClip, AudioFileClip
    from PIL import Image, ImageDraw, ImageFont
    import whisper
except ImportError as e:
    print("ERRO: Uma ou mais dependências não estão instaladas:", e)
    print("Por favor, execute no terminal: pip install opencv-python mediapipe numpy tqdm moviepy Pillow openai-whisper")
    sys.exit(1)


def draw_subtitle_pil(frame_bgr, text, frame_width):
    """
    Desenha texto (com acentos) sobre o frame BGR, retornando BGR.
    Usa uma faixa semitransparente atrás do texto.
    """
    frame_rgba = Image.fromarray(cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)).convert("RGBA")
    overlay = Image.new("RGBA", frame_rgba.size, (255, 255, 255, 0))
    draw = ImageDraw.Draw(overlay)

    # Procura por fontes comuns, se não usar padrão
    font_candidates = [
        "arial.ttf",
        os.path.join("C:\\Windows\\Fonts", "arial.ttf"),
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
    ]
    font = None
    font_size = max(24, int(frame_width / 20))
    for p in font_candidates:
        try:
            if os.path.exists(p):
                font = ImageFont.truetype(p, font_size)
                break
        except Exception:
            font = None
    if font is None:
        font = ImageFont.load_default()

    # quebra em linhas para caber na largura
    max_width = int(frame_width * 0.9)
    words = text.split()
    lines = []
    cur = ""
    for w in words:
        test = (cur + " " + w).strip()
        bbox = draw.textbbox((0,0), test, font=font)
        tw = bbox[2] - bbox[0]
        if tw <= max_width:
            cur = test
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)

    try:
        line_h = font.getbbox("Mg")[3] - font.getbbox("Mg")[1]
    except Exception:
        line_h = font.getsize("A")[1]

    spacing = int(line_h * 0.3)
    total_h = len(lines) * (line_h + spacing) - spacing
    y = frame_rgba.height - total_h - int(frame_rgba.height * 0.06)

    for line in lines:
        bbox = draw.textbbox((0,0), line, font=font)
        tw = bbox[2] - bbox[0]
        x = (frame_rgba.width - tw) // 2
        # desenha retângulo semitransparente
        pad = 10
        draw.rectangle([x-pad, y-pad, x+tw+pad, y+line_h+pad], fill=(0,0,0,150))
        draw.text((x, y), line, font=font, fill=(255,255,255,255))
        y += line_h + spacing

    combined = Image.alpha_composite(frame_rgba, overlay)
    out_bgr = cv2.cvtColor(np.array(combined.convert("RGB")), cv2.COLOR_RGB2BGR)
    return out_bgr


def process_video(input_path, output_path, out_h=1080, legenda="on", start=None, end=None):
    """
    Função principal: cria crop vertical 9:16 focado em rosto, gera legendas (opcional)
    e escreve arquivo final com áudio.
    start/end: None ou strings 'HH:MM:SS' ou 'MM:SS'
    legenda: 'on'/'off'
    """
    if not os.path.exists(input_path):
        raise FileNotFoundError(f"Arquivo não encontrado: {input_path}")

    # Carrega Whisper (modelo base para menor uso de RAM; mude para 'medium' se quiser)
    print("🗣️ Carregando Whisper (base)...")
    model = whisper.load_model("base")  # troque para "medium" se tiver memória e GPU

    print("🎬 Abrindo vídeo com MoviePy...")
    video_full = VideoFileClip(input_path)
    # subclip se start/end passados
    start_time = start if start and start.strip() != "" else None
    end_time = end if end and end.strip() != "" else None
    video = video_full.subclip(start_time, end_time) if (start_time or end_time) else video_full

    # extrai áudio temporário
    audio_tmp = tempfile.mktemp(suffix=".mp3")
    video.audio.write_audiofile(audio_tmp, logger=None)

    # gerar legendas com whisper (se pedido)
    subtitle_segments = []
    if legenda.lower() == "on":
        print("🗣️ Gerando legendas com Whisper (pode demorar)...")
        result = model.transcribe(audio_tmp, language="pt", fp16=False)
        subtitle_segments = result.get("segments", [])
        print(f"✅ Legendas geradas: {len(subtitle_segments)} segmentos")

    # --- configurações de crop 9:16 ---
    target_h = int(out_h)
    target_w = int(round(target_h * 9 / 16))

    mp_face_mesh = mp.solutions.face_mesh
    face_mesh = mp_face_mesh.FaceMesh(static_image_mode=False, max_num_faces=2,
                                      refine_landmarks=True, min_detection_confidence=0.5,
                                      min_tracking_confidence=0.5)

    # estado de tracking para suavização
    last_cx, last_cy = None, None
    smoothing = 0.15  # suavização exponencial (0..1)

    fps = video.fps

    # função que MoviePy usa para gerar frames processados
    def process_frame(get_frame, t):
        nonlocal last_cx, last_cy
        frame_rgb = get_frame(t)  # MoviePy fornece frame em RGB
        h, w, _ = frame_rgb.shape

        # converte para BGR para usar cv2 quando necessário
        frame_bgr = cv2.cvtColor(frame_rgb, cv2.COLOR_RGB2BGR)

        # detecção de face (MediaPipe espera RGB)
        results = face_mesh.process(frame_rgb)
        cx, cy = w // 2, h // 2
        if results.multi_face_landmarks:
            # pega a maior face detectada
            best = None
            best_area = 0
            for lm in results.multi_face_landmarks:
                xs = [p.x * w for p in lm.landmark]
                ys = [p.y * h for p in lm.landmark]
                xm, xM = min(xs), max(xs)
                ym, yM = min(ys), max(ys)
                area = (xM - xm) * (yM - ym)
                if area > best_area:
                    best_area = area
                    best = ( (xm+xM)/2.0, (ym+yM)/2.0 )
            if best is not None:
                cx = int(best[0])
                cy = int(best[1])

        # suavização (evita puxadas bruscas)
        if last_cx is None:
            last_cx, last_cy = cx, cy
        else:
            last_cx = int(last_cx * (1 - smoothing) + cx * smoothing)
            last_cy = int(last_cy * (1 - smoothing) + cy * smoothing)
            cx, cy = last_cx, last_cy

        # crop 9:16 centrado em (cx,cy) sem esticar (apenas cortar)
        crop_h = target_h
        crop_w = target_w
        # limita bordas
        x1 = int(max(0, min(cx - crop_w // 2, w - crop_w)))
        y1 = int(max(0, min(cy - crop_h // 2, h - crop_h)))
        cropped = frame_bgr[y1:y1+crop_h, x1:x1+crop_w]

        # se alguma dimensão for menor (vídeo menor que target), faz pad com preto
        ch, cw = cropped.shape[:2]
        if ch != crop_h or cw != crop_w:
            canvas = np.zeros((crop_h, crop_w, 3), dtype=np.uint8)
            canvas[0:ch, 0:cw] = cropped
            cropped = canvas

        # legenda: procura segmento que contenha t (segundos desde início do subclip)
        if subtitle_segments:
            text = ""
            for seg in subtitle_segments:
                if seg["start"] <= t <= seg["end"]:
                    text = seg["text"].strip()
                    break
            if text:
                # desenha legenda sobre BGR
                cropped = draw_subtitle_pil(cropped, text, crop_w)

        # retorna RGB (MoviePy espera RGB)
        out_rgb = cv2.cvtColor(cropped, cv2.COLOR_BGR2RGB)
        return out_rgb

    # cria clip processado com MoviePy (mantém áudio depois)
    print("🎬 Processando clip (pode demorar dependendo do vídeo)...")
    processed = video.fl(process_frame, apply_to=["video"])

    # escreve vídeo final (mescla áudio original)
    print("🎶 Renderizando e mesclando áudio...")
    processed.set_audio(VideoFileClip(input_path).subclip(start, end).audio if (start or end) else video.audio)\
             .write_videofile(output_path, codec="libx264", audio_codec="aac", threads=0, logger="bar")

    # limpeza
    face_mesh.close()
    try:
        os.remove(audio_tmp)
    except Exception:
        pass

    print("✅ Processamento finalizado:", output_path)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Transforma horizontais em verticais com legendas.")
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--out_h", type=int, default=1080)
    parser.add_argument("--legenda", choices=["on","off"], default="on")
    parser.add_argument("--start", type=str, default=None)
    parser.add_argument("--end", type=str, default=None)
    args = parser.parse_args()

    process_video(args.input, args.output, out_h=args.out_h, legenda=args.legenda, start=args.start, end=args.end)
