import os
import argparse
import tempfile
import cv2
import numpy as np
from moviepy.editor import VideoFileClip, AudioFileClip
from PIL import Image, ImageDraw, ImageFont
import mediapipe as mp
import whisper


def draw_subtitle_pil(frame_bgr, text, width):
    """Desenha legenda no frame com fundo semitransparente."""
    text = str(text).encode('utf-8', 'ignore').decode('utf-8')
    font_path = "C:\\Windows\\Fonts\\arial.ttf" if os.name == "nt" else "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
    font = ImageFont.truetype(font_path, 36)
    img_pil = Image.fromarray(frame_bgr)
    draw = ImageDraw.Draw(img_pil, "RGBA")
    text_bbox = draw.textbbox((0, 0), text, font=font)
    text_w = text_bbox[2] - text_bbox[0]
    text_h = text_bbox[3] - text_bbox[1]
    x = (width - text_w) // 2
    y = img_pil.height - text_h - 30
    draw.rectangle((x - 20, y - 10, x + text_w + 20, y + text_h + 10), fill=(0, 0, 0, 128))
    draw.text((x, y), text, font=font, fill=(255, 255, 255, 255))
    return np.array(img_pil)


def process_video(input_path, output_path, out_h=1080, legenda="on", start=None, end=None):
    """Processa vídeo: recorte vertical com rastreamento facial e legendas automáticas."""
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

        subtitle_dict = {}
        if legenda.lower() == "on":
            print("🗣️  Gerando legendas automáticas com Whisper... Isso pode demorar.")
            result = model.transcribe(audio_path, language="pt", fp16=False)
            for seg in result["segments"]:
                subtitle_dict[(seg["start"], seg["end"])] = seg["text"]

        # Configura o MediaPipe FaceMesh
        mp_face_mesh = mp.solutions.face_mesh
        face_mesh = mp_face_mesh.FaceMesh(
            static_image_mode=False,
            max_num_faces=1,
            min_detection_confidence=0.5
        )
        tracking_state = {'last_cx': -1, 'last_cy': -1}

        def process_frame(get_frame, t):
            frame = get_frame(t)
            h, w, _ = frame.shape
            target_aspect_ratio = 9 / 16
            crop_h = out_h
            crop_w = int(crop_h * target_aspect_ratio)
            crop_w -= (crop_w % 2)

            cx, cy = w // 2, h // 2
            results = face_mesh.process(frame)
            if results.multi_face_landmarks:
                lm = results.multi_face_landmarks[0].landmark
                x_coords = [l.x * w for l in lm]
                y_coords = [l.y * h for l in lm]
                cx, cy = int(np.mean(x_coords)), int(np.mean(y_coords))
                if tracking_state['last_cx'] == -1:
                    tracking_state['last_cx'], tracking_state['last_cy'] = cx, cy

            if tracking_state['last_cx'] != -1:
                cx = int(tracking_state['last_cx'] * 0.9 + cx * 0.1)
                cy = int(tracking_state['last_cy'] * 0.9 + cy * 0.1)

            tracking_state['last_cx'], tracking_state['last_cy'] = cx, cy

            x1 = max(0, min(cx - crop_w // 2, w - crop_w))
            y1 = max(0, min(cy - crop_h // 2, h - crop_h))
            cropped_frame_rgb = frame[y1:y1 + crop_h, x1:x1 + crop_w]

            # Adiciona legenda se habilitado
            if legenda.lower() == "on":
                text = ""
                for (s, e), ttext in subtitle_dict.items():
                    if s <= t <= e:
                        text = str(ttext).encode('utf-8', 'ignore').decode('utf-8')
                        break
                if text:
                    cropped_frame_bgr = cv2.cvtColor(cropped_frame_rgb, cv2.COLOR_RGB2BGR)
                    processed_bgr = draw_subtitle_pil(cropped_frame_bgr, text.strip(), crop_w)
                    cropped_frame_rgb = cv2.cvtColor(processed_bgr, cv2.COLOR_BGR2RGB)

            return cropped_frame_rgb

        processed_clip = video.fl(process_frame)

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


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Auto vertical crop com rastreamento facial e legendas automáticas.")
    parser.add_argument("--input", required=True, help="Caminho do vídeo de entrada.")
    parser.add_argument("--output", required=True, help="Caminho do vídeo de saída.")
    parser.add_argument("--out_h", type=int, default=1080, help="Altura do vídeo de saída (padrão: 1080).")
    parser.add_argument("--legenda", type=str, default="on", help="Ativar legendas automáticas (on/off).")
    parser.add_argument("--start", type=str, default=None, help="Tempo inicial (ex: 00:00:10).")
    parser.add_argument("--end", type=str, default=None, help="Tempo final (ex: 00:01:30).")
    args = parser.parse_args()

    process_video(args.input, args.output, args.out_h, args.legenda, args.start, args.end)
