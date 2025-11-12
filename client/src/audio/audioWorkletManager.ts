/**
 * AudioWorklet 管理器
 * 管理 AudioWorklet 的加载和音频处理
 */

export interface AudioFrameMetadata {
  seq: number;
  t0: number;
  sr: number;
  channels: number;
  frameCount: number;
  rms?: number;
}

export interface AudioWorkletCallbacks {
  onAudioFrame?: (data: ArrayBuffer, metadata: AudioFrameMetadata) => void;
  onError?: (error: Error) => void;
}

export class AudioWorkletManager {
  private audioContext: AudioContext | null = null;
  private workletNode: AudioWorkletNode | null = null;
  private sourceNode: MediaStreamAudioSourceNode | null = null;
  private stream: MediaStream | null = null;
  private callbacks: AudioWorkletCallbacks = {};
  private isInitialized = false;

  /**
   * 初始化 AudioWorklet
   */
  async initialize(stream: MediaStream, callbacks: AudioWorkletCallbacks = {}): Promise<void> {
    if (this.isInitialized) {
      throw new Error('AudioWorklet already initialized');
    }

    this.stream = stream;
    this.callbacks = callbacks;

    try {
      // 创建 AudioContext（固定 16kHz，与测试保持一致）
      // 注意：即使设备不支持 16kHz，AudioContext 也会自动处理
      this.audioContext = new AudioContext({ 
        sampleRate: 16000,
        latencyHint: 'interactive'
      });
      const actualSampleRate = this.audioContext.sampleRate; // 获取实际采样率

      // 加载 AudioWorklet 模块
      await this.audioContext.audioWorklet.addModule('/audio/audio-processor.worklet.js');

      // 创建 AudioWorkletNode
      this.workletNode = new AudioWorkletNode(
        this.audioContext,
        'audio-processor',
        {
          numberOfInputs: 1,
          numberOfOutputs: 0, // 不需要输出
          processorOptions: {}
        }
      );

      // 设置消息处理器
      this.workletNode.port.onmessage = (event) => {
        try {
          if (event.data.type === 'ready') {
            // 发送初始化参数
            this.workletNode!.port.postMessage({
              type: 'init',
              sampleRate: actualSampleRate
            });
          } else if (event.data.type === 'audio') {
            // 处理音频帧
            if (this.callbacks.onAudioFrame) {
              this.callbacks.onAudioFrame(
                event.data.data,
                {
                  seq: event.data.seq,
                  t0: event.data.t0,
                  sr: event.data.sr,
                  channels: event.data.channels,
                  frameCount: event.data.frameCount,
                  rms: event.data.rms
                }
              );
            }
          }
        } catch (error) {
          console.error('[AudioWorklet] Message handler error:', error);
          if (this.callbacks.onError) {
            this.callbacks.onError(error as Error);
          }
        }
      };

      // 创建源节点
      this.sourceNode = this.audioContext.createMediaStreamSource(stream);

      // 连接节点
      this.sourceNode.connect(this.workletNode);

      // 确保 AudioContext 运行
      if (this.audioContext.state === 'suspended') {
        await this.audioContext.resume();
      }

      this.isInitialized = true;
      console.log('✅ AudioWorklet initialized');
    } catch (error) {
      console.error('❌ AudioWorklet initialization failed:', error);
      throw error;
    }
  }

  /**
   * 停止音频处理
   */
  stop(): void {
    if (this.workletNode) {
      this.workletNode.disconnect();
      this.workletNode = null;
    }

    if (this.sourceNode) {
      this.sourceNode.disconnect();
      this.sourceNode = null;
    }

    if (this.audioContext && this.audioContext.state !== 'closed') {
      this.audioContext.close();
      this.audioContext = null;
    }

    if (this.stream) {
      this.stream.getTracks().forEach(track => track.stop());
      this.stream = null;
    }

    this.isInitialized = false;
    console.log('🛑 AudioWorklet stopped');
  }

  /**
   * 检查是否已初始化
   */
  get initialized(): boolean {
    return this.isInitialized;
  }
}

