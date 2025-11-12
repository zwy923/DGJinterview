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
        // 使用 AudioContext 的实际采样率（通常是 16kHz 或浏览器默认值）
        this.actualSampleRate = event.data.sampleRate || 16000;
        this.resampleRatio = this.targetSampleRate / this.actualSampleRate;
        console.log(`[AudioWorklet] 初始化: actualSR=${this.actualSampleRate}, targetSR=${this.targetSampleRate}, ratio=${this.resampleRatio}`);
        this.port.postMessage({ type: 'ready' });
      }
    };
  }

  /**
   * 线性重采样（简单实现，生产环境建议使用 WASM/SoXR）
   * 注意：如果采样率已经匹配，直接返回，避免不必要的处理
   */
  resample(input, inputRate, outputRate) {
    if (Math.abs(inputRate - outputRate) < 1) {
      return input; // 采样率相同，直接返回
    }
    
    const ratio = outputRate / inputRate;
    const outputLength = Math.floor(input.length * ratio);
    if (outputLength <= 0) {
      return new Float32Array(0);
    }
    
    const output = new Float32Array(outputLength);
    
    for (let i = 0; i < outputLength; i++) {
      const srcIndex = i / ratio;
      const srcIndexFloor = Math.floor(srcIndex);
      const srcIndexCeil = Math.min(srcIndexFloor + 1, input.length - 1);
      const t = srcIndex - srcIndexFloor;
      
      // 线性插值
      if (srcIndexFloor >= 0 && srcIndexFloor < input.length) {
        output[i] = input[srcIndexFloor] * (1 - t) + input[srcIndexCeil] * t;
      } else {
        output[i] = 0;
      }
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
    
    // 累积到批次缓冲区（修复溢出问题）
    let audioIndex = 0;
    while (audioIndex < processedAudio.length) {
      // 计算本次可以填充的数量
      const remaining = this.batchSize - this.batchIndex;
      const toCopy = Math.min(remaining, processedAudio.length - audioIndex);
      
      // 复制数据到批次缓冲区
      this.batchBuffer.set(processedAudio.subarray(audioIndex, audioIndex + toCopy), this.batchIndex);
      this.batchIndex += toCopy;
      audioIndex += toCopy;
      
      // 当批次缓冲区满（200ms）时发送
      if (this.batchIndex >= this.batchSize) {
        const pcmData = this.floatToInt16(this.batchBuffer);
        const rms = this.calculateRMS(this.batchBuffer);
        
        // 发送音频帧（带元数据）
        const timestamp = this.frameCount / this.targetSampleRate;
        try {
          this.port.postMessage({
            type: 'audio',
            data: pcmData.buffer,
            seq: this.seq++,
            t0: timestamp,
            sr: this.targetSampleRate,
            channels: 1,
            frameCount: this.batchSize,
            rms: rms
          }, [pcmData.buffer]);
        } catch (e) {
          // 如果 postMessage 失败，继续处理（避免阻塞）
          console.error('[AudioWorklet] postMessage failed:', e);
        }
        
        this.frameCount += this.batchSize;
        
        // 重置批次缓冲区
        this.batchIndex = 0;
        this.batchBuffer = new Float32Array(this.batchSize);
      }
    }
    
    return true;
  }
}

registerProcessor('audio-processor', AudioProcessor);

