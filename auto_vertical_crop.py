"""
Auto Vertical Crop + Legendas + Trecho do Vídeo
Transforma vídeos horizontais em verticais, com foco automático em rostos,
detecção de fala, legenda e possibilidade de selecionar trecho do vídeo.
"""

import argparse
import cv2
import mediapipe as mp
import numpy as np
from tqdm import tqdm

# --------------------------- Configurações ---------------------------
THRESH_MOUTH_OPEN = 0.035
SMOOTHING = 0.2
ALT_INTERVAL_FRAMES = 60
OUTPUT_HEIGHT_DEFAULT = 1080
ASPECT_W = 9
ASPECT_H = 16

mp_face_mesh = mp.solutions.face_mesh

# --------------------------- Funções utilitárias ---------------------------
def landmarks_to_bbox(landmarks, frame_w, frame_h):
    xs = np.array([lm.x for lm in landmarks]) * frame_w
    ys = np.array([lm.y for lm in landmarks]) * frame_h
    x_min = int(np.min(xs))
    x_max = int(np.max(xs))
    y_min = int(np.min(ys))
    y_max = int(np.max(ys))
    return x_min, y_min, x_max - x_min, y_max - y_min

def mouth_open_ratio(landmarks, frame_h):
    ys = np.array([lm.y for lm in landmarks])
    y_min = np.min(ys)
    y_max = np.max(ys)
    face_h = y_max - y_min
    if face_h <= 0:
        return 0.0
    lower_thresh = y_min + face_h * 0.5
    mouth_region_idxs = np.where((ys >= lower_thresh) & (ys <= y_max))[0]
    if len(mouth_region_idxs) < 3:
        return 0.0
    mouth_ys = ys[mouth_region_idxs]
    mouth_open_rel = np.max(mouth_ys) - np.min(mouth_ys)
    return mouth_open_rel / face_h

def draw_subtitle(frame, text, font_scale=1.0, thickness=2):
    h, w, _ = frame.shape
    font = cv2.FONT_HERSHEY_SIMPLEX
    text_size = cv2.getTextSize(text, font, font_scale, thickness)[0]
    text_x = (w - text_size[0]) // 2
    text_y = h - 30
    overlay = frame.copy()
    cv2.rectangle(overlay, (text_x - 10, text_y - text_size[1] - 10),
                  (text_x + text_size[0] + 10, text_y + 10), (0,0,0), -1)
    alpha = 0.5
    frame = cv2.addWeighted(overlay, alpha, frame, 1 - alpha, 0)
    cv2.putText(frame, text, (text_x, text_y), font, font_scale, (255,255,255), thickness, cv2.LINE_AA)
    return frame

def time_to_seconds(time_str):
    """Converte 'HH:MM:SS', 'MM:SS' ou 'SS' para segundos"""
    parts = [int(p) for p in time_str.split(':')]
    if len(parts) == 3:
        h, m, s = parts
    elif len(parts) == 2:
        h = 0
        m, s = parts
    else:
        h = 0
        m = 0
        s = parts[0]
    return h*3600 + m*60 + s

# --------------------------- Processamento do vídeo ---------------------------
def process_video(input_path, output_path, out_h=OUTPUT_HEIGHT_DEFAULT, smoothing=SMOOTHING,
                  thresh_mouth=THRESH_MOUTH_OPEN, alt_interval=ALT_INTERVAL_FRAMES,
                  start_sec=0, end_sec=None):

    cap = cv2.VideoCapture(input_path)
    if not cap.isOpened():
        raise RuntimeError(f"Não foi possível abrir o arquivo: {input_path}")

    frame_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    frame_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)

    out_h = int(out_h)
    out_w = int(round(out_h * ASPECT_W / ASPECT_H))
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    out = cv2.VideoWriter(output_path, fourcc, fps, (out_w, out_h))

    # converte start/end para frames
    start_frame = int(start_sec * fps)
    end_frame = int(end_sec * fps) if end_sec else total_frames

    cur_cx = frame_w // 2
    cur_cy = frame_h // 2

    with mp_face_mesh.FaceMesh(static_image_mode=False,
                               max_num_faces=6,
                               refine_landmarks=True,
                               min_detection_confidence=0.5,
                               min_tracking_confidence=0.5) as face_mesh:

        pbar = tqdm(total=end_frame - start_frame, desc='Processando frames')
        frame_idx = 0

        while True:
            ret, frame = cap.read()
            if not ret or frame_idx > end_frame:
                break

            if frame_idx < start_frame:
                frame_idx += 1
                continue

            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            results = face_mesh.process(frame_rgb)

            faces = []
            if results.multi_face_landmarks:
                for i, face_landmarks in enumerate(results.multi_face_landmarks):
                    lm = face_landmarks.landmark
                    x_min, y_min, w_box, h_box = landmarks_to_bbox(lm, frame_w, frame_h)
                    cx = x_min + w_box / 2
                    cy = y_min + h_box / 2
                    mouth_ratio = mouth_open_ratio(lm, frame_h)
                    is_speaking = mouth_ratio >= thresh_mouth
                    faces.append({
                        'center': (cx, cy),
                        'area': w_box * h_box,
                        'is_speaking': is_speaking,
                        'id': i,
                    })

            # decisão do foco
            target_cx = frame_w / 2
            target_cy = frame_h / 2
            subtitle_text = "Ninguém na cena"

            if len(faces) == 1:
                target_cx, target_cy = faces[0]['center']
                subtitle_text = "Falando" if faces[0]['is_speaking'] else "Foco alternado"
            elif len(faces) > 1:
                speaking_faces = [f for f in faces if f['is_speaking']]
                if speaking_faces:
                    chosen = max(speaking_faces, key=lambda f: f['area'])
                    target_cx, target_cy = chosen['center']
                    subtitle_text = "Falando"
                else:
                    idx = (frame_idx // alt_interval) % len(faces)
                    chosen = faces[idx]
                    target_cx, target_cy = chosen['center']
                    subtitle_text = "Foco alternado"

            # suavização exponencial
            cur_cx = (1 - smoothing) * cur_cx + smoothing * target_cx
            cur_cy = (1 - smoothing) * cur_cy + smoothing * target_cy

            # crop seguro
            crop_w = min(out_w, frame_w)
            crop_h = min(out_h, frame_h)
            x1 = max(0, min(int(cur_cx - crop_w // 2), frame_w - crop_w))
            y1 = max(0, min(int(cur_cy - crop_h // 2), frame_h - crop_h))
            crop = frame[y1:y1 + crop_h, x1:x1 + crop_w]
            if crop.shape[0] != out_h or crop.shape[1] != out_w:
                crop = cv2.resize(crop, (out_w, out_h), interpolation=cv2.INTER_LINEAR)

            crop = draw_subtitle(crop, subtitle_text)
            out.write(crop)
            frame_idx += 1
            pbar.update(1)

        pbar.close()
    cap.release()
    out.release()
    print(f"✅ Processamento concluído. Arquivo salvo em: {output_path}")

# --------------------------- CLI ---------------------------
if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Auto Vertical Crop + Legendas + Trecho do vídeo')
    parser.add_argument('--input', '-i', required=True, help='Arquivo de entrada (vídeo horizontal)')
    parser.add_argument('--output', '-o', required=True, help='Arquivo de saída .mp4')
    parser.add_argument('--out_h', type=int, default=OUTPUT_HEIGHT_DEFAULT, help='Altura do vídeo de saída (px)')
    parser.add_argument('--smoothing', type=float, default=SMOOTHING, help='Coeficiente de suavização (0-1)')
    parser.add_argument('--mouth_thresh', type=float, default=THRESH_MOUTH_OPEN, help='Limiar para boca aberta')
    parser.add_argument('--alt_interval', type=int, default=ALT_INTERVAL_FRAMES, help='Frames por rosto ao alternar quando ninguém fala')
    parser.add_argument('--start', type=str, default="0:0:0", help='Tempo inicial (SS, MM:SS ou HH:MM:SS)')
    parser.add_argument('--end', type=str, default=None, help='Tempo final (SS, MM:SS ou HH:MM:SS)')

    args = parser.parse_args()
    start_sec = time_to_seconds(args.start)
    end_sec = time_to_seconds(args.end) if args.end else None

    process_video(
        input_path=args.input,
        output_path=args.output,
        out_h=args.out_h,
        smoothing=args.smoothing,
        thresh_mouth=args.mouth_thresh,
        alt_interval=args.alt_interval,
        start_sec=start_sec,
        end_sec=end_sec
    )
