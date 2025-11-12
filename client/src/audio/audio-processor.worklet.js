/**
 * AudioWorklet 音频处理器
 * 在音频线程中处理音频数据，降低主线程阻塞
 */

class AudioProcessor extends AudioWorkletProcessor {
  constructor() {
    super();
    this.bufferSize = 1600; // 100ms @ 16kHz
    this.buffer = new Float32Array(this.bufferSize);
    this.bufferIndex = 0;
    this.frameCount = 0;
    this.seq = 0;
    this.targetSampleRate = 16000;
    this.actualSampleRate = 16000; // 将在初始化时设置
    
    // 重采样相关
    this.resampleBuffer = [];
    this.resampleRatio = 1.0;
    
    // 批次发送（200ms）
    this.batchSize = 3200; // 200ms @ 16kHz
    this.batchBuffer = new Float32Array(this.batchSize);
    this.batchIndex = 0;
    
    this.port.onmessage = (event) => {
      if (event.data.type === 'init') {
        this.actualSampleRate = event.data.sampleRate || 16000;
        this.resampleRatio = this.targetSampleRate / this.actualSampleRate;
        this.port.postMessage({ type: 'ready' });
      }
    };
  }

  /**
   * 线性重采样（简单实现，生产环境建议使用 WASM/SoXR）
   */
  resample(input, inputRate, outputRate) {
    if (inputRate === outputRate) {
      return input;
    }
    
    const ratio = outputRate / inputRate;
    const outputLength = Math.floor(input.length * ratio);
    const output = new Float32Array(outputLength);
    
    for (let i = 0; i < outputLength; i++) {
      const srcIndex = i / ratio;
      const srcIndexFloor = Math.floor(srcIndex);
      const srcIndexCeil = Math.min(srcIndexFloor + 1, input.length - 1);
      const t = srcIndex - srcIndexFloor;
      
      // 线性插值
      output[i] = input[srcIndexFloor] * (1 - t) + input[srcIndexCeil] * t;
    }
    
    return output;
  }

  /**
   * 计算 RMS（浮点域）
   */
  calculateRMS(audio) {
    let sum = 0;
    for (let i = 0; i < audio.length; i++) {
      sum += audio[i] * audio[i];
    }
    return Math.sqrt(sum / audio.length);
  }

  /**
   * 转换为 Int16 PCM
   */
  floatToInt16(floatArray) {
    const int16Array = new Int16Array(floatArray.length);
    for (let i = 0; i < floatArray.length; i++) {
      const sample = Math.max(-1, Math.min(1, floatArray[i]));
      int16Array[i] = Math.round(sample * 32767);
    }
    return int16Array;
  }

  process(inputs, outputs, parameters) {
    const input = inputs[0];
    if (input.length === 0 || input[0].length === 0) {
      return true;
    }

    const inputChannel = input[0];
    
    // 重采样到 16kHz（如果需要）
    let processedAudio = inputChannel;
    if (this.actualSampleRate !== this.targetSampleRate) {
      processedAudio = this.resample(inputChannel, this.actualSampleRate, this.targetSampleRate);
    }
    
    // 累积到批次缓冲区
    for (let i = 0; i < processedAudio.length; i++) {
      if (this.batchIndex < this.batchSize) {
        this.batchBuffer[this.batchIndex++] = processedAudio[i];
      }
      
      // 当批次缓冲区满（200ms）时发送
      if (this.batchIndex >= this.batchSize) {
        const pcmData = this.floatToInt16(this.batchBuffer);
        const rms = this.calculateRMS(this.batchBuffer);
        
        // 发送音频帧（带元数据）
        this.port.postMessage({
          type: 'audio',
          data: pcmData.buffer,
          seq: this.seq++,
          t0: currentFrame / this.targetSampleRate,
          sr: this.targetSampleRate,
          channels: 1,
          frameCount: this.batchSize,
          rms: rms
        }, [pcmData.buffer]);
        
        // 重置批次缓冲区
        this.batchIndex = 0;
        this.batchBuffer = new Float32Array(this.batchSize);
      }
    }
    
    return true;
  }
}

registerProcessor('audio-processor', AudioProcessor);

