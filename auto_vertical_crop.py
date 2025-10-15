import cv2
import mediapipe as mp
import numpy as np
import moviepy.editor as mpedit
import whisper
import argparse
import tempfile
import os
from tqdm import tqdm

# ===============================
# Função para gerar legendas com Whisper
# ===============================
def gerar_legendas(audio_path):
    model = whisper.load_model("base")
    result = model.transcribe(audio_path, language="pt")
    legendas = []
    for seg in result["segments"]:
        legendas.append({
            "start": seg["start"],
            "end": seg["end"],
            "text": seg["text"]
        })
    return legendas

# ===============================
# Função principal de crop vertical
# ===============================
def processar_video(input_path, output_path, start, end, out_h, legenda_on):
    mp_pose = mp.solutions.pose.Pose()
    cap = cv2.VideoCapture(input_path)
    fps = cap.get(cv2.CAP_PROP_FPS)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

    # Define recorte vertical
    out_w = int(out_h * 9 / 16)
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')

    temp_video = tempfile.NamedTemporaryFile(delete=False, suffix='.mp4')
    out = cv2.VideoWriter(temp_video.name, fourcc, fps, (out_w, out_h))

    start_frame = int(start * fps)
    end_frame = int(end * fps) if end else total_frames
    cap.set(cv2.CAP_PROP_POS_FRAMES, start_frame)

    cx_suave = width // 2

    for i in tqdm(range(start_frame, min(end_frame, total_frames)), desc="Processando vídeo"):
        ret, frame = cap.read()
        if not ret:
            break

        # Detecção com MediaPipe
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        res = mp_pose.process(rgb)
        if res.pose_landmarks:
            pontos = res.pose_landmarks.landmark
            xs = [p.x * width for p in pontos if p.visibility > 0.5]
            if xs:
                cx = np.mean(xs)
                cx_suave = int(0.8 * cx_suave + 0.2 * cx)
        else:
            cx = width // 2

        x1 = max(0, int(cx_suave - out_w // 2))
        x2 = min(width, x1 + out_w)
        crop = frame[0:height, x1:x2]

        if crop.shape[1] != out_w:
            crop = cv2.resize(crop, (out_w, out_h))

        out.write(crop)

    cap.release()
    out.release()

    # ===============================
    # Gera vídeo final com MoviePy
    # ===============================
    clip = mpedit.VideoFileClip(temp_video.name).subclip(start, end)
    audio = mpedit.VideoFileClip(input_path).audio.subclip(start, end)
    clip = clip.set_audio(audio)

    if legenda_on:
        # Extrair áudio para Whisper
        temp_audio = tempfile.NamedTemporaryFile(delete=False, suffix='.mp3')
        clip.audio.write_audiofile(temp_audio.name, verbose=False, logger=None)

        legendas = gerar_legendas(temp_audio.name)
        clips_legenda = []
        for seg in legendas:
            txt = mpedit.TextClip(seg["text"], fontsize=40, color="white", stroke_color="black", stroke_width=2, size=(out_w - 40, None), method='caption')
            txt = txt.set_start(seg["start"]).set_end(seg["end"]).set_position(("center", out_h - 100))
            clips_legenda.append(txt)
        final = mpedit.CompositeVideoClip([clip, *clips_legenda])
        temp_audio.close()
    else:
        final = clip

    final.write_videofile(output_path, codec='libx264', audio_codec='aac', threads=4)
    os.remove(temp_video.name)

# ===============================
# Argumentos do CMD
# ===============================
if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--start", type=str, default="00:00:00")
    parser.add_argument("--end", type=str, default=None)
    parser.add_argument("--out_h", type=int, default=1080)
    parser.add_argument("--legenda", type=str, default="off")
    args = parser.parse_args()

    def parse_time(t):
        h, m, s = map(int, t.split(":"))
        return h * 3600 + m * 60 + s

    start = parse_time(args.start)
    end = parse_time(args.end) if args.end else None
    legenda_on = args.legenda.lower() == "on"

    processar_video(args.input, args.output, start, end, args.out_h, legenda_on)
