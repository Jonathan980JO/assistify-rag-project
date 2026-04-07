import wave
import struct
import pyttsx3

def generate_tts():
    engine = pyttsx3.init()
    engine.save_to_file('What is the weather today?', 'speech_tmp.wav')
    engine.runAndWait()
    
    with wave.open('speech_tmp.wav', 'rb') as wf:
        nframes = wf.getnframes()
        framerate = wf.getframerate()
        sampwidth = wf.getsampwidth()
        nchannels = wf.getnchannels()
        data = wf.readframes(nframes)
    
    silence_frames = framerate * 4 # 4 seconds of silence
    silence_data = b'\x00' * (silence_frames * sampwidth * nchannels)
    
    with wave.open('speech_44100.wav', 'wb') as wf:
        wf.setnchannels(nchannels)
        wf.setsampwidth(sampwidth)
        wf.setframerate(framerate)
        wf.writeframes(data + silence_data)
        
    print(f"Generated speech_44100.wav with {sampwidth*8}-bit {framerate}Hz rate and padded silence.")

generate_tts()
