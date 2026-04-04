import pyaudio
import numpy as np

pa = pyaudio.PyAudio()

print("HOST API & FORMAT SWEEP")
print("=" * 60)

for api_idx in range(pa.get_host_api_count()):
    api_info = pa.get_host_api_info_by_index(api_idx)
    api_name = api_info.get('name')
    print(f"\n[API] {api_name} (Index: {api_idx})")
    
    for dev_idx in range(pa.get_device_count()):
        dev_info = pa.get_device_info_by_index(dev_idx)
        if dev_info['hostApi'] != api_idx or dev_info['maxInputChannels'] == 0:
            continue
            
        if "X-PRO" not in dev_info['name']:
            continue
            
        print(f"  Device: {dev_info['name']} (Index: {dev_idx})")
        
        # Test 16kHz Mono Int16
        try:
            stream = pa.open(
                format=pyaudio.paInt16,
                channels=1,
                rate=16000,
                input=True,
                input_device_index=dev_idx
            )
            data = stream.read(8000, exception_on_overflow=False) # 0.5 sec
            stream.close()
            audio = np.frombuffer(data, dtype=np.int16).astype(np.float32) / 32768.0
            rms = np.sqrt(np.mean(audio**2))
            mean = np.mean(audio)
            print(f"    16kHz Mono Int16 -> RMS: {rms:.6f}, Mean: {mean:.6f}")
        except Exception as e:
            print(f"    16kHz Mono Int16 -> FAILED: {str(e)[:50]}")

        # Test 44.1kHz Stereo Int16
        try:
            stream = pa.open(
                format=pyaudio.paInt16,
                channels=2,
                rate=44100,
                input=True,
                input_device_index=dev_idx
            )
            data = stream.read(22050, exception_on_overflow=False) # 0.5 sec
            stream.close()
            audio = np.frombuffer(data, dtype=np.int16).reshape(-1, 2).astype(np.float32) / 32768.0
            rms_l = np.sqrt(np.mean(audio[:, 0]**2))
            rms_r = np.sqrt(np.mean(audio[:, 1]**2))
            print(f"    44kHz Stereo Int16 -> RMS L: {rms_l:.6f}, RMS R: {rms_r:.6f}")
        except Exception as e:
            print(f"    44kHz Stereo Int16 -> FAILED: {str(e)[:50]}")

pa.terminate()
