from pygame import *
import sounddevice as sd
import scipy.io.wavfile as wav
import numpy as np
import os
import threading

# === Налаштування звуку та екрану ===
fs = 44100     # Частота дискретизації
chunk = 1024   # Розмір кадру для візуалізації звуку
duration = 10  # Тривалість запису в секундах
width, height = 800, 500  

# Назви файлів у папці проєкту
MINUS_FILE = "minus.wav"
VOICE_FILE = "voice_record.wav"

init()
screen = display.set_mode((width, height))
display.set_caption("Cyberpunk Studio - Mic Recorder")
clock = time.Clock()

# Початкові дані — масив нулів
data = [0.0] * chunk
is_recording = False
is_playing = False  # Нова змінна для відстеження відтворення

# Шрифти для виведення тексту на екран
font.init()
main_font = font.SysFont("Courier", 24, bold=True)
sub_font = font.SysFont("Courier", 18)

# Створення прямокутників для кнопок
btn_rec_rect = Rect(50, 400, 200, 50)
btn_play_rect = Rect(300, 400, 250, 50)

# Початкові рівні гучності (від 0.0 до 2.0)
vol_minus = 1.0
vol_voice = 1.0

# === Потік для фонового відтворення готового міксу ===
current_playback_stream = None

def play_mix_process():
    global is_playing
    if not os.path.exists(VOICE_FILE):
        print("Спочатку потрібно зробити запис голосу!")
        return
    try:
        is_playing = True
        # Зчитуємо записаний голос користувача
        _, v_data = wav.read(VOICE_FILE)
        v_data = v_data.astype(np.float32) / 32768.0
        if len(v_data.shape) == 1:
            v_data = np.column_stack((v_data, v_data))
        
        # Зчитуємо оригінальну мінусовку
        if os.path.exists(MINUS_FILE):
            _, m_data = wav.read(MINUS_FILE)
            m_data = m_data.astype(np.float32) / 32768.0
            if len(m_data.shape) == 1:
                m_data = np.column_stack((m_data, m_data))
            
            # Міксуємо з урахуванням виставленої гучності
            min_len = min(len(v_data), len(m_data))
            mix = (v_data[:min_len] * vol_voice) + (m_data[:min_len] * vol_minus)
        else:
            mix = v_data * vol_voice
            
        sd.play(mix, fs)
        sd.wait()
    except Exception as e:
        print("Помилка під час відтворення:", e)
    is_playing = False

# === Потік для одночасного запису голосу та програвання мінуса ===
def record_process():
    global is_recording, data
    is_recording = True
    
    total_frames = int(duration * fs)
    minus_track = None
    
    # Спробуємо завантажити мінусовку "minus.wav"
    if os.path.exists(MINUS_FILE):
        try:
            sr, m_data = wav.read(MINUS_FILE)
            if m_data.dtype == np.int16:
                m_data = m_data.astype(np.float32) / 32768.0
            
            if len(m_data.shape) == 1:
                m_data = np.column_stack((m_data, m_data))
            
            if len(m_data) < total_frames:
                pad = np.zeros((total_frames - len(m_data), 2), dtype=np.float32)
                minus_track = np.vstack((m_data, pad))
            else:
                minus_track = m_data[:total_frames]
        except Exception as e:
            print("Не вдалося завантажити мінус:", e)

    try:
        if minus_track is not None:
            print(f"Запуск спільного запису з мінусом (Гучність мінуса: {int(vol_minus*100)}%)...")
            # Застосовуємо гучність мінуса безпосередньо перед стартом запису!
            recorded_audio = sd.playrec(minus_track * vol_minus, samplerate=fs, channels=1, dtype='float32')
            
            for i in range(0, total_frames, chunk):
                if not is_recording: 
                    break
                sd.sleep(int((chunk / fs) * 1000))
                
                chunk_data = recorded_audio[i:i+chunk]
                if len(chunk_data) == chunk:
                    data = [sample * (200 // 2) for sample in chunk_data[:, 0].tolist()]
            
            sd.wait()
            voice_int = (recorded_audio * 32767).astype(np.int16)
            wav.write(VOICE_FILE, fs, voice_int)
        else:
            print("Мінусовку не знайдено, пишемо чистий голос...")
            recorded_audio = sd.rec(total_frames, samplerate=fs, channels=1, dtype='float32')
            
            for i in range(0, total_frames, chunk):
                sd.sleep(int((chunk / fs) * 1000))
                chunk_data = recorded_audio[i:i+chunk]
                if len(chunk_data) == chunk:
                    data = [sample * (200 // 2) for sample in chunk_data[:, 0].tolist()]
                    
            sd.wait()
            voice_int = (recorded_audio * 32767).astype(np.int16)
            wav.write(VOICE_FILE, fs, voice_int)
            
        print("Запис голосу успішно збережено!")
            
    except Exception as e:
        print("Помилка під час запису:", e)
        
    is_recording = False

# Функція для "живого" мікрофона, коли програма просто відкрита
def audio_callback(indata, frames, time_info, status):
    global data
    if status:
        print(status)
    data = [sample * (200 // 2) for sample in indata[:, 0].tolist()]

main_stream = sd.InputStream(callback=audio_callback, channels=1, samplerate=fs, blocksize=chunk, dtype='float32')
main_stream.start()

# === Головний ігровий цикл програми ===
running = True
while running:
    for e in event.get():
        if e.type == QUIT:
            running = False
        
        # Перевірка кліків мишки
        if e.type == MOUSEBUTTONDOWN:
            mouse_pos = e.pos
            
            if btn_rec_rect.collidepoint(mouse_pos) and not is_recording and not is_playing:
                main_stream.stop()
                threading.Thread(target=record_process, daemon=True).start()
            
            if btn_play_rect.collidepoint(mouse_pos) and not is_recording and not is_playing:
                threading.Thread(target=play_mix_process, daemon=True).start()
                
        # Обробка натискань стрілочок (виставляємо гучність)
        if e.type == KEYDOWN:
            if e.key == K_UP:    vol_voice = min(2.0, vol_voice + 0.1)
            if e.key == K_DOWN:  vol_voice = max(0.0, vol_voice - 0.1)
            if e.key == K_RIGHT: vol_minus = min(2.0, vol_minus + 0.1) # Стрілка вправо — голосніше
            if e.key == K_LEFT:  vol_minus = max(0.0, vol_minus - 0.1) # Стрілка вліво — тихіше

    if not is_recording and not main_stream.active:
        main_stream.start()

    screen.fill((13, 12, 29))

    # Сітка осцилографа
    for x in range(0, width, 40):
        draw.line(screen, (20, 20, 50), (x, 0), (x, 300), 1)
    for y in range(0, 300, 40):
        draw.line(screen, (20, 20, 50), (0, y), (width, y), 1)

    # Малювання хвилі звуку
    points = []
    for i, sample in enumerate(data):
        x = int(i * width / chunk)
        y = int(150 + sample)
        points.append((x, y))

    if len(points) > 1:
        draw.lines(screen, (57, 255, 20), False, points, 2)

    # Кнопка Запису
    rec_color = (85, 85, 85) if is_recording else (255, 0, 127)
    draw.rect(screen, rec_color, btn_rec_rect, border_radius=5)
    rec_text = main_font.render("ЗАПИСУЄТЬСЯ..." if is_recording else "ЗАПИС", True, (255, 255, 255))
    screen.blit(rec_text, (btn_rec_rect.x + 20, btn_rec_rect.y + 12))

    # Кнопка відтворення
    play_color = (85, 85, 85) if is_playing else (0, 240, 255)
    draw.rect(screen, play_color, btn_play_rect, border_radius=5)
    play_text = main_font.render("ПРОГРАЄТЬСЯ..." if is_playing else "ПРОСЛУХАТИ МІКС", True, (13, 12, 29))
    screen.blit(play_text, (btn_play_rect.x + 15, btn_play_rect.y + 12))

    # Текст рівнів гучності
    txt_vol_v = sub_font.render(f"Гучність голосу (Вгору/Вниз): {int(vol_voice*100)}%", True, (57, 255, 20))
    txt_vol_m = sub_font.render(f"Гучність мінуса (Вліво/Вправо): {int(vol_minus*100)}%", True, (0, 240, 255))
    screen.blit(txt_vol_v, (50, 320))
    screen.blit(txt_vol_m, (50, 350))

    display.update()
    clock.tick(60)

main_stream.stop()
quit()
