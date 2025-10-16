import os
import tempfile
import cv2
import numpy as np
from moviepy.editor import VideoFileClip, AudioFileClip
from PIL import Image, ImageDraw, ImageFont
import mediapipe as mp
import whisper
import sys
import shutil
import textwrap

# --- FFmpeg: tenta usar PATH ou ffmpeg.exe na pasta ---
ffmpeg_candidates = ["ffmpeg", os.path.join(os.getcwd(), "ffmpeg.exe")]
ffmpeg_found = any(shutil.which(cmd) or os.path.exists(cmd) for cmd in ffmpeg_candidates)
if not ffmpeg_found:
    print("⚠️  Aviso: FFmpeg não encontrado no PATH. Coloque ffmpeg.exe na pasta do script ou instale no sistema.")

def draw_subtitle_pil(frame_bgr, text, width):
    """Desenha legenda no frame com fundo semitransparente, ajustando tamanho e quebrando linhas."""
    text = str(text).encode('utf-8', 'ignore').decode('utf-8')
    font_path = "C:\\Windows\\Fonts\\arial.ttf" if os.name == "nt" else "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
    
    # Ajusta fonte dinamicamente
    font_size = 36
    while font_size > 12:
        font = ImageFont.truetype(font_path, font_size)
        # Quebra o texto em múltiplas linhas
        lines = textwrap.wrap(text, width=int(width / (font_size * 0.6)))
        line_heights = [font.getbbox(line)[3] - font.getbbox(line)[1] for line in lines]
        total_height = sum(line_heights) + 10 * len(lines)
        if total_height + 30 < frame_bgr.shape[0] * 0.35:  # não ocupa mais que 35% da altura
            break
        font_size -= 2

    img_pil = Image.fromarray(frame_bgr)
    draw = ImageDraw.Draw(img_pil, "RGBA")

    # calcula posição inicial da legenda (de cima para baixo, dentro do frame)
    y = img_pil.height - total_height - 20
    for line, line_h in zip(lines, line_heights):
        text_bbox = draw.textbbox((0, 0), line, font=font)
        text_w = text_bbox[2] - text_bbox[0]
        x = (width - text_w) // 2
        draw.rectangle((x - 10, y - 5, x + text_w + 10, y + line_h + 5), fill=(0, 0, 0, 128))
        draw.text((x, y), line, font=font, fill=(255, 255, 255, 255))
        y += line_h + 10

    return np.array(img_pil)

def process_video(input_path, output_path, out_h=1080, legenda="on", start=None, end=None):
    """Processa vídeo: recorte vertical centralizado no rosto, sem esticar, com legendas automáticas."""
    if not os.path.exists(input_path):
        print(f"ERRO: O arquivo de entrada não foi encontrado em '{input_path}'")
        return

    try:
        print("🗣️  Carregando Whisper (base)...")
        model = whisper.load_model("base")

        print("🎬 Lendo o arquivo de vídeo...")
        video_full = VideoFileClip(input_path)

        start_time = start.strip() if start else None
        end_time = end.strip() if end else None
        video = video_full.subclip(start_time, end_time) if start_time or end_time else video_full

        # Extrai o áudio temporariamente
        audio_path = tempfile.mktemp(suffix=".mp3")
        video.audio.write_audiofile(audio_path, logger=None)

        # Geração de legendas
        subtitle_dict = {}
        if legenda.lower() == "on":
            print("🗣️  Gerando legendas automáticas com Whisper... Isso pode demorar.")
            result = model.transcribe(audio_path, language="pt", fp16=False)
            for seg in result["segments"]:
                subtitle_dict[(seg["start"], seg["end"])] = seg["text"]

        # Configura MediaPipe FaceMesh
        mp_face_mesh = mp.solutions.face_mesh
        face_mesh = mp_face_mesh.FaceMesh(static_image_mode=False, max_num_faces=1, min_detection_confidence=0.5)
        tracking_state = {'last_cx': -1, 'last_cy': -1}

        def process_frame(get_frame, t):
            frame = get_frame(t)
            h, w, _ = frame.shape

            target_aspect_ratio = 9 / 16
            crop_h = h
            crop_w = int(crop_h * target_aspect_ratio)

            if crop_w > w:  # ajusta altura se a largura exceder
                crop_w = w
                crop_h = int(crop_w / target_aspect_ratio)

            # centro do rosto
            cx, cy = w // 2, h // 2
            results = face_mesh.process(frame)
            if results.multi_face_landmarks:
                lm = results.multi_face_landmarks[0].landmark
                x_coords = [l.x * w for l in lm]
                y_coords = [l.y * h for l in lm]
                cx, cy = int(np.mean(x_coords)), int(np.mean(y_coords))
                if tracking_state['last_cx'] == -1:
                    tracking_state['last_cx'], tracking_state['last_cy'] = cx, cy

            # suavização do rastreamento
            if tracking_state['last_cx'] != -1:
                cx = int(tracking_state['last_cx'] * 0.9 + cx * 0.1)
                cy = int(tracking_state['last_cy'] * 0.9 + cy * 0.1)
            tracking_state['last_cx'], tracking_state['last_cy'] = cx, cy

            # recorte vertical sem esticar
            x1 = max(0, min(cx - crop_w // 2, w - crop_w))
            y1 = max(0, min(cy - crop_h // 2, h - crop_h))
            cropped_frame_rgb = frame[y1:y1 + crop_h, x1:x1 + crop_w]

            # adiciona legenda
            if legenda.lower() == "on":
                text = ""
                for (s, e), ttext in subtitle_dict.items():
                    if s <= t <= e:
                        text = str(ttext).encode('utf-8', 'ignore').decode('utf-8')
                        break
                if text:
                    cropped_frame_bgr = cv2.cvtColor(cropped_frame_rgb, cv2.COLOR_RGB2BGR)
                    processed_bgr = draw_subtitle_pil(cropped_frame_bgr, text.strip(), cropped_frame_rgb.shape[1])
                    cropped_frame_rgb = cv2.cvtColor(processed_bgr, cv2.COLOR_BGR2RGB)

            return cropped_frame_rgb

        processed_clip = video.fl(process_frame)

        # Força largura e altura pares (necessário para x264)
        final_w = processed_clip.w - processed_clip.w % 2
        final_h = processed_clip.h - processed_clip.h % 2
        processed_clip = processed_clip.resize((final_w, final_h))

        print("🎶 Montando o vídeo final com áudio...")
        processed_clip.set_audio(AudioFileClip(audio_path)).write_videofile(
            output_path,
            codec="libx264",
            audio_codec="aac",
            logger=None,
            ffmpeg_params=['-pix_fmt', 'yuv420p']
        )

        face_mesh.close()
        os.remove(audio_path)
        print(f"✅ Concluído! Vídeo salvo em: {output_path}")

    except Exception as e:
        print(f"❌ Erro durante o processamento: {e}")
        raise e

# --- Permite execução via CLI ---
if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Auto vertical crop com rastreamento facial e legendas automáticas.")
    parser.add_argument("--input", required=True, help="Caminho do vídeo de entrada.")
    parser.add_argument("--output", required=True, help="Caminho do vídeo de saída.")
    parser.add_argument("--out_h", type=int, default=1080, help="Altura do vídeo de saída (padrão: 1080).")
    parser.add_argument("--legenda", type=str, default="on", help="Ativar legendas automáticas (on/off).")
    parser.add_argument("--start", type=str, default=None, help="Tempo inicial (ex: 00:00:10).")
    parser.add_argument("--end", type=str, default=None, help="Tempo final (ex: 00:01:30).")
    args = parser.parse_args()

    process_video(args.input, args.output, args.out_h, args.legenda, args.start, args.end)
