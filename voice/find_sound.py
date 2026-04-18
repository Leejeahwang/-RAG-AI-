import pyaudio
import numpy as np
import time

pa = pyaudio.PyAudio()

print("Audio Device Monitor")
print("Detecting active audio input devices...")
print("-" * 60)

devices = []
for i in range(pa.get_device_count()):
    info = pa.get_device_info_by_index(i)
    if info['maxInputChannels'] > 0:
        devices.append(i)

start_time = time.time()
max_rms = {i: 0.0 for i in devices}

try:
    while time.time() - start_time < 5: # Reduced to 5 seconds for efficiency
        for idx in devices:
            info = pa.get_device_info_by_index(idx)
            try:
                rate = int(info['defaultSampleRate'])
                stream = pa.open(
                    format=pyaudio.paInt16,
                    channels=1,
                    rate=rate,
                    input=True,
                    input_device_index=idx,
                    frames_per_buffer=1024
                )
                data = stream.read(1024, exception_on_overflow=False)
                stream.close()
                audio = np.frombuffer(data, dtype=np.int16).astype(np.float32) / 32768.0
                rms = np.abs(audio).mean()
                if rms > max_rms[idx]:
                    max_rms[idx] = rms
            except:
                pass
        print(f"Sampling... {int(5 - (time.time() - start_time))}s remaining", end="\r")

    print("\n\nAnalysis Results (Sorted by Intensity):")
    results = sorted(max_rms.items(), key=lambda x: x[1], reverse=True)
    for idx, rms in results:
        info = pa.get_device_info_by_index(idx)
        api_info = pa.get_host_api_info_by_index(info['hostApi'])
        print(f"Index {idx:2d}: Peak {rms:.4f} | {info['name']} ({api_info['name']})")

finally:
    pa.terminate()
