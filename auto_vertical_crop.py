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
except ImportError:
    print("ERRO: Uma ou mais dependências não estão instaladas.")
    print("Por favor, execute o comando no seu terminal:")
    print("pip install -r requirements.txt")
    sys.exit(1)


def draw_subtitle_pil(frame, text, frame_width):
    """
    @description Desenha o texto da legenda com fundo semitransparente e melhor espaçamento.
    """
    frame_pil = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)).convert("RGBA")
    overlay = Image.new("RGBA", frame_pil.size, (255, 255, 255, 0))
    draw = ImageDraw.Draw(overlay)

    font_options = [
        os.path.join("src", "fonts", "arial.ttf"),
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/Library/Fonts/Arial.ttf",
        "/usr/share/fonts/truetype/msttcorefonts/Arial.ttf"
    ]
    
    selected_font = None
    font_size = max(28, int(frame_width / 18))

    # Tenta carregar a fonte Arial nos caminhos mais comuns
    for path in font_options:
        if os.path.exists(path):
            try:
                font = ImageFont.truetype(path, font_size)
                selected_font = font
                break
            except Exception:
                continue

    # Fallback para a fonte padrão do Pillow
    if selected_font is None:
        print(f"\nAtenção: Nenhuma fonte Arial encontrada. Usando fonte padrão.")
        font = ImageFont.load_default()
        selected_font = font
    
    font = selected_font

    max_width = frame_width * 0.9
    words = text.split()
    lines = []
    current_line = []
    
    for word in words:
        test_line = " ".join(current_line + [word])
        bbox = draw.textbbox((0, 0), test_line, font=font)
        text_w = bbox[2] - bbox[0]

        if text_w <= max_width:
            current_line.append(word)
        else:
            if current_line: 
                lines.append(" ".join(current_line))
            current_line = [word]
            
            if draw.textbbox((0, 0), word, font=font)[2] - draw.textbbox((0, 0), word, font=font)[0] > max_width:
                 if not current_line:
                    current_line.append(word)

    if current_line:
        lines.append(" ".join(current_line))

    try:
        line_height = font.getbbox("Tg")[3] - font.getbbox("Tg")[1]
    except AttributeError:
        line_height = font.getsize("A")[1] 
    
    spacing = int(line_height * 0.5)
    total_line_height = line_height + spacing

    total_text_height = len(lines) * total_line_height - spacing if lines else 0
    y_start = frame_pil.height - total_text_height - int(frame_pil.height * 0.1)

    for i, line in enumerate(lines):
        bbox_line = draw.textbbox((0, 0), line, font=font)
        text_width = bbox_line[2] - bbox_line[0]

        x = (frame_width - text_width) / 2
        y = y_start + (i * total_line_height)

        background_padding = 10
        bg_x0 = max(0, x - background_padding)
        bg_y0 = y - background_padding
        bg_x1 = min(frame_width, x + text_width + background_padding)
        bg_y1 = min(frame_pil.height, y + line_height + background_padding)
        draw.rectangle([bg_x0, bg_y0, bg_x1, bg_y1], fill=(0, 0, 0, 150))

        draw.text((x, y), line, font=font, fill=(255, 255, 255, 255))

    combined = Image.alpha_composite(frame_pil, overlay)
    
    return cv2.cvtColor(np.array(combined), cv2.COLOR_RGBA2BGR)


# Removida a classe CustomLogger

def process_video(input_path, output_path, out_h=1080, legenda="on", start=None, end=None):
    """
    @description Função principal que carrega um vídeo, detecta rostos para criar um corte vertical,
                 gera legendas automáticas e renderiza o vídeo final.
    """
    if not os.path.exists(input_path):
        print(f"ERRO: O arquivo de entrada não foi encontrado em '{input_path}'")
        return

    try:
        # Removido custom_logger = CustomLogger(stream=sys.stdout)
        
        print("🗣️  Carregando Whisper (base)...")
        model = whisper.load_model("base") 
        
        print("🎬 Lendo o arquivo de vídeo...")
        video_full = VideoFileClip(input_path) 

        start_time = start if start and start.strip() != "" else None
        end_time = end if end and end.strip() != "" else None
        
        video = video_full.subclip(start_time, end_time) if start_time or end_time else video_full
        
        audio_path = tempfile.mktemp(suffix=".mp3")
        video.audio.write_audiofile(audio_path, logger=None)
        
        subtitle_dict = {}
        if legenda.lower() == "on":
            print("🗣️  Gerando legendas automáticas com Whisper... Isso pode demorar.")
            result = model.transcribe(audio_path, language="pt", fp16=False)
            for seg in result["segments"]:
                subtitle_dict[(seg["start"], seg["end"])] = seg["text"]
                
        mp_face_mesh = mp.solutions.face_mesh
        face_mesh = mp_face_mesh.FaceMesh(static_image_mode=False, max_num_faces=1, min_detection_confidence=0.5)
        
        tracking_state = {'last_cx': -1, 'last_cy': -1}

        def process_frame(get_frame, t):
            frame = get_frame(t)
            h, w, _ = frame.shape
            
            target_aspect_ratio = 9.0 / 16.0
            crop_h = out_h
            crop_w = int(crop_h * target_aspect_ratio)
            crop_w -= (crop_w % 2)
            
            cx, cy = w // 2, h // 2
            
            results = face_mesh.process(frame)
            
            if results.multi_face_landmarks:
                lm = results.multi_face_landmarks[0].landmark
                x_coords = [landmark.x * w for landmark in lm]
                y_coords = [landmark.y * h for landmark in lm]
                cx, cy = int(np.mean(x_coords)), int(np.mean(y_coords))
                if tracking_state['last_cx'] == -1:
                    tracking_state['last_cx'], tracking_state['last_cy'] = cx, cy

            if tracking_state['last_cx'] != -1:
                cx = int(tracking_state['last_cx'] * 0.9 + cx * 0.1)
                cy = int(tracking_state['last_cy'] * 0.1 + cy * 0.1)
            
            tracking_state['last_cx'], tracking_state['last_cy'] = cx, cy

            x1 = max(0, cx - crop_w // 2)
            y1 = max(0, cy - crop_h // 2)
            if x1 + crop_w > w: x1 = w - crop_w
            if y1 + crop_h > h: y1 = h - crop_h
            x1 = max(0, x1)
            y1 = max(0, y1)
            
            cropped_frame_rgb = frame[y1:y1+crop_h, x1:x1+crop_w]
            
            if legenda.lower() == "on":
                text = ""
                for (start_t, end_t), s_text in subtitle_dict.items():
                    if start_t <= t <= end_t:
                        text = s_text
                        break
                if text:
                    cropped_frame_bgr = cv2.cvtColor(cropped_frame_rgb, cv2.COLOR_RGB2BGR)
                    processed_frame_bgr = draw_subtitle_pil(cropped_frame_bgr, text.strip(), crop_w)
                    cropped_frame_rgb = cv2.cvtColor(processed_frame_bgr, cv2.COLOR_BGR2RGB)

            return cropped_frame_rgb

        processed_clip = video.fl(process_frame)

        print("🎶 Montando o vídeo final com áudio...")
        processed_clip.set_audio(AudioFileClip(audio_path)).write_videofile(
            output_path, 
            codec="libx264", 
            audio_codec="aac", 
            logger='bar', # Usa logger nativo do MoviePy
            ffmpeg_params=['-pix_fmt', 'yuv420p']
        )

        face_mesh.close()
        os.remove(audio_path)
        print(f"✅ Concluído! Vídeo salvo em: {output_path}")

    except Exception as e:
        # A exceção é levantada para ser capturada pelo processo principal (GUI)
        raise e


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Transforma vídeos horizontais em verticais com foco em rostos e legendas.")
    parser.add_argument("--input", required=True, help="Caminho para o vídeo de entrada. Ex: video.mp4")
    parser.add_argument("--output", required=True, help="Caminho para o vídeo de saída. Ex: video_vertical.mp4")
    parser.add_argument("--out_h", type=int, default=1080, help="Altura do vídeo de saída em pixels.")
    parser.add_argument("--legenda", type=str, default="on", choices=['on', 'off'], help="Adicionar legendas automáticas ('on' ou 'off').")
    parser.add_argument("--start", type=str, default=None, help="Tempo de início do corte. Formato: hh:mm:ss ou mm:ss")
    parser.add_argument("--end", type=str, default=None, help="Tempo de fim do corte. Formato: hh:mm:ss ou mm:ss")
    args = parser.parse_args()
    
    process_video(args.input, args.output, out_h=args.out_h,
                  legenda=args.legenda, start=args.start, end=args.end)