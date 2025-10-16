import sys
import os
import tempfile
import argparse
import numpy as np

# Bloco para verificar dependências antes de qualquer outra coisa
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
    @param frame O frame (imagem) onde o texto será desenhado.
    @param text O texto da legenda a ser exibido.
    @param frame_width A largura do frame para cálculo de centralização.
    @return O frame com a legenda desenhada.
    """
    frame_pil = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)).convert("RGBA")
    overlay = Image.new("RGBA", frame_pil.size, (255, 255, 255, 0))
    draw = ImageDraw.Draw(overlay)

    font_path = os.path.join("src", "fonts", "arial.ttf")
    font_size = max(28, int(frame_width / 18))
    try:
        font = ImageFont.truetype(font_path, font_size)
    except IOError:
        print(f"\nAtenção: Fonte não encontrada em '{font_path}'. Usando fonte padrão.")
        font = ImageFont.load_default()

    max_width = frame_width * 0.9
    words = text.split()
    lines = []
    current_line = ""
    for word in words:
        if draw.textbbox((0, 0), current_line + word, font=font)[2] <= max_width:
            current_line += word + " "
        else:
            lines.append(current_line.strip())
            current_line = word + " "
    lines.append(current_line.strip())

    line_height = font.getbbox("A")[3]
    spacing = int(line_height * 0.5)
    total_line_height = line_height + spacing

    total_text_height = len(lines) * total_line_height - spacing
    y_start = frame_pil.height - total_text_height - int(frame_pil.height * 0.1)

    for i, line in enumerate(lines):
        text_bbox = draw.textbbox((0, 0), line, font=font)
        text_width = text_bbox[2] - text_bbox[0]
        x = (frame_width - text_width) / 2
        y = y_start + (i * total_line_height)

        background_padding = 10
        bg_x0 = x - background_padding
        bg_y0 = y - background_padding
        bg_x1 = x + text_width + background_padding
        bg_y1 = y + line_height + background_padding
        draw.rectangle([bg_x0, bg_y0, bg_x1, bg_y1], fill=(0, 0, 0, 128))

        draw.text((x, y), line, font=font, fill=(255, 255, 255, 255))

    combined = Image.alpha_composite(frame_pil, overlay)
    
    return cv2.cvtColor(np.array(combined), cv2.COLOR_RGBA2BGR)


def process_video(input_path, output_path, out_h=1080, legenda="on", start=None, end=None):
    """
    @description Função principal que carrega um vídeo, detecta rostos para criar um corte vertical,
                 gera legendas automáticas e renderiza o vídeo final.
    @param input_path Caminho para o vídeo de entrada.
    @param output_path Caminho para salvar o vídeo processado.
    @param out_h Altura final do vídeo em pixels.
    @param legenda 'on' para gerar legendas, 'off' para pular.
    @param start Tempo de início do corte (e.g., '00:10').
    @param end Tempo de fim do corte (e.g., '00:55').
    """
    if not os.path.exists(input_path):
        print(f"ERRO: O arquivo de entrada não foi encontrado em '{input_path}'")
        return

    try:
        print("🗣️  Carregando Whisper (base)...")
        model = whisper.load_model("base") 
        
        print("🎬 Lendo o arquivo de vídeo...")
        video_full = VideoFileClip(input_path)

        if end and video_full.duration < video_full.subclip(0, end).end:
             print(f"ERRO: O tempo final ({end}) é maior que a duração total do vídeo ({video_full.duration:.2f}s).")
             return
        if start and video_full.duration < video_full.subclip(0, start).end:
             print(f"ERRO: O tempo inicial ({start}) é maior que a duração total do vídeo ({video_full.duration:.2f}s).")
             return

        video = video_full.subclip(start, end) if start or end else video_full
        
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
            codec="libx264", # ✅ CORREÇÃO: De 'libx24' para 'libx264'
            audio_codec="aac", 
            logger='bar',
            ffmpeg_params=['-pix_fmt', 'yuv420p']
        )

        face_mesh.close()
        os.remove(audio_path)
        print(f"✅ Concluído! Vídeo salvo em: {output_path}")

    except Exception as e:
        print("\n--- OCORREU UM ERRO INESPERADO ---")
        print(f"Erro: {e}")
        print("Verifique se o arquivo de vídeo não está corrompido e se os parâmetros estão corretos.")


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