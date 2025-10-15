# Videos-na-vertical
Transforma vídeos na horizontal para a vertical, dando zoom em rostos e adicionando legenda, além de poder delimitar qual parte do video você quer ser editada.
---
# Como usar:
### 1°-Coloque o código dentro de uma pasta com o vídeo que você quer alterar.
### 2°-Abra o cmd da pasta,escreva:
##### python -m pip install opencv-python mediapipe numpy tqdm moviepy
##### pip install openai-whisper
### 3°-Coloque no cmd:
##### python auto_vertical_crop.py --input XX.mp4 --output XX_vertical.mp4 --start hh:mm:ss --end hh:mm:ss --out_h 1080
-XX é o nome do vídeo que será adicionado na pasta. hh:mm:ss (hora/minuto/segundo) é o tempo do corte do vídeo que começa e que termina, respectivamente.
