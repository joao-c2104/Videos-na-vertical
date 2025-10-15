"""
Auto Vertical Crop + Legendas (compatível com vídeos grandes)
Converte vídeos horizontais para verticais com foco automático em rostos,
detecção de fala e legenda indicativa.
"""

import argparse
import cv2
import mediapipe as mp
import numpy as np
from tqdm import tqdm

# --------------------------- Configurações ---------------------------
THRESH_MOUTH_OPEN = 0.035   # limiar heurístico para boca aberta
SMOOTHING = 0.2             # suavização exponencial do centro
ALT_INTERVAL_FRAMES = 60    # alterna foco a cada N frames se ninguém fala
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
    # Fundo semitransparente
    overlay = frame.copy()
    cv2.rectangle(overlay, (text_x - 10, text_y - text_size[1] - 10),
                  (text_x + text_size[0] + 10, text_y + 10), (0,0,0), -1)
    alpha = 0.5
    frame = cv2.addWeighted(overlay, alpha, frame, 1 - alpha, 0)
    cv2.putText(frame, text, (text_x, text_y), font, font_scale, (255,255,255), thickness, cv2.LINE_AA)
    return frame

# --------------------------- Processamento do vídeo ---------------------------
def process_video(input_path, output_path, out_h=OUTPUT_HEIGHT_DEFAULT, smoothing=SMOOTHING,
                  thresh_mouth=THRESH_MOUTH_OPEN, alt_interval=ALT_INTERVAL_FRAMES):

    cap = cv2.VideoCapture(input_path)
    if not cap.isOpened():
        raise RuntimeError(f"Não foi possível abrir o arquivo: {input_path}")

    frame_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    frame_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0

    out_h = int(out_h)
    out_w = int(round(out_h * ASPECT_W / ASPECT_H))

    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    out = cv2.VideoWriter(output_path, fourcc, fps, (out_w, out_h))

    cur_cx = frame_w // 2
    cur_cy = frame_h // 2

    with mp_face_mesh.FaceMesh(static_image_mode=False,
                               max_num_faces=6,
                               refine_landmarks=True,
                               min_detection_confidence=0.5,
                               min_tracking_confidence=0.5) as face_mesh:

        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        pbar = tqdm(total=total_frames, desc='Processando frames')

        frame_idx = 0

        while True:
            ret, frame = cap.read()
            if not ret:
                break

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
                        'landmarks': lm,
                        'bbox': (x_min, y_min, w_box, h_box),
                        'center': (cx, cy),
                        'area': w_box * h_box,
                        'mouth_ratio': mouth_ratio,
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

            # crop 9:16 seguro
            crop_w = min(out_w, frame_w)
            crop_h = min(out_h, frame_h)

            x1 = max(0, min(int(cur_cx - crop_w // 2), frame_w - crop_w))
            y1 = max(0, min(int(cur_cy - crop_h // 2), frame_h - crop_h))

            crop = frame[y1:y1 + crop_h, x1:x1 + crop_w]

            # redimensiona para a resolução de saída final
            if crop.shape[0] != out_h or crop.shape[1] != out_w:
                crop = cv2.resize(crop, (out_w, out_h), interpolation=cv2.INTER_LINEAR)

            # adiciona legenda
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
    parser = argparse.ArgumentParser(description='Auto Vertical Crop + Legendas')
    parser.add_argument('--input', '-i', required=True, help='Arquivo de entrada (vídeo horizontal)')
    parser.add_argument('--output', '-o', required=True, help='Arquivo de saída .mp4')
    parser.add_argument('--out_h', type=int, default=OUTPUT_HEIGHT_DEFAULT, help='Altura do vídeo de saída (px)')
    parser.add_argument('--smoothing', type=float, default=SMOOTHING, help='Coeficiente de suavização (0-1)')
    parser.add_argument('--mouth_thresh', type=float, default=THRESH_MOUTH_OPEN, help='Limiar para boca aberta')
    parser.add_argument('--alt_interval', type=int, default=ALT_INTERVAL_FRAMES, help='Frames por rosto ao alternar quando ninguém fala')

    args = parser.parse_args()
    process_video(args.input, args.output, out_h=args.out_h, smoothing=args.smoothing,
                  thresh_mouth=args.mouth_thresh, alt_interval=args.alt_interval)
